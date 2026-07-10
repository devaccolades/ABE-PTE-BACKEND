import os
import uuid
import tempfile
from urllib.parse import urlencode
from django.db import DatabaseError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from .models import Question, MockTest, MockTestSection, UserResponse, UserMockTestSession, SubQuestion,Section,SubSection,SingleResponse
from .serializers import UserMockTestSession,SingleQuestionSerializer,UserResponseSerializer,MockTestListSerializer,QuestionSerializer,SingleResponseSerializer 
from .services.transcription import transcribe_and_analyse
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView
from rest_framework.exceptions import NotFound
from .services.pdf_service import generate_session_pdf
from .services.evaluation_status import build_session_evaluation_status
from .services.evaluation_queue import (
    EvaluationQueueUnavailable,
    queue_response_evaluation,
)
from django.http import FileResponse


def normalize_question_lookup(question_id=None, question_name=None):
    if question_id:
        try:
            return int(question_id), None, None
        except (TypeError, ValueError):
            return None, None, "invalid_id"

    if question_name:
        return None, question_name, None

    return None, None, "missing"


def get_session_question(mock_test, question_id=None, question_name=None):
    question_id, question_name, lookup_error = normalize_question_lookup(
        question_id=question_id,
        question_name=question_name,
    )
    if lookup_error:
        return None, lookup_error

    questions = Question.objects.filter(mock_test_section__mock_test=mock_test)

    if question_id:
        questions = questions.filter(id=question_id)
    else:
        questions = questions.filter(name=question_name)

    count = questions.count()

    if count == 0:
        return None, "not_found"
    if count > 1:
        return None, "duplicate"

    return questions.select_related("subsection").first(), None


def get_single_question(question_id=None, question_name=None):
    question_id, question_name, lookup_error = normalize_question_lookup(
        question_id=question_id,
        question_name=question_name,
    )
    if lookup_error:
        return None, lookup_error

    if question_id:
        questions = Question.objects.filter(id=question_id)
    else:
        questions = Question.objects.filter(name=question_name)

    count = questions.count()

    if count == 0:
        return None, "not_found"
    if count > 1:
        return None, "duplicate"

    return questions.select_related("subsection").first(), None


class SessionPDFView(APIView):
    def get(self, request, pk):
        session = get_object_or_404(UserMockTestSession, pk=pk)

        file_path = f"/tmp/session_{session.id}.pdf"

        generate_session_pdf(session, file_path)

        return FileResponse(
            open(file_path, "rb"),
            as_attachment=True,
            filename=f"session_{session.id}.pdf"
        )


class SessionEvaluationStatusAPIView(APIView):
    def get(self, request):
        session_id = request.query_params.get("session_id")
        include_responses = (
            request.query_params.get("include_responses", "false").lower() == "true"
        )

        if not session_id:
            return Response(
                {"error": "session_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            session = UserMockTestSession.objects.select_related("mock_test").get(
                session_id=session_id,
            )
        except UserMockTestSession.DoesNotExist:
            return Response(
                {"error": "Invalid session_id"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            build_session_evaluation_status(
                session,
                include_responses=include_responses,
            ),
            status=status.HTTP_200_OK,
        )


class QuestionPagination(PageNumberPagination):
    page_size = 10                    # default
    page_size_query_param = "page_size"
    max_page_size = 50


class SubSectionQuestionListAPIView(ListAPIView):
    serializer_class = SingleQuestionSerializer
    # pagination_class = QuestionPagination

    def get_queryset(self):
        subsection_name = self.kwargs.get("subsection_name")

        try:
            subsection = SubSection.objects.get(name=subsection_name)
        except SubSection.DoesNotExist:
            raise NotFound("Invalid subsection name")

        return (
            Question.objects
            .filter(subsection=subsection)
             .select_related(
                'mock_test_section',
                'mock_test_section__section',
                'subsection'
            )
            .prefetch_related(
                'options',
                'sub_questions__options'
            )
            .order_by(
                'mock_test_section__order',
                'subsection__order',
                'id'
            )[:10]
        )

class SingleAPIView(APIView):
    def post(self, request):
        question_id = request.data.get('question_id')
        question_name = request.data.get('question_name')
        name = request.data.get('name')
        answer = request.data.get('answer')
        audio_file = request.FILES.get('answer_audio')

        question, question_error = get_single_question(
            question_id=question_id,
            question_name=question_name,
        )

        if question_error == "not_found":
            return Response({"error": "Invalid question"}, status=status.HTTP_404_NOT_FOUND)
        if question_error == "invalid_id":
            return Response({"error": "question_id must be a valid integer"}, status=status.HTTP_400_BAD_REQUEST)
        if question_error == "missing":
            return Response({"error": "question_id or question_name is required"}, status=status.HTTP_400_BAD_REQUEST)
        if question_error == "duplicate":
            return Response(
                {"error": "Duplicate question_name. Use question_id."},
                status=status.HTTP_409_CONFLICT,
            )

                    
        user_answer = SingleResponse.objects.create(
            name= name,
            question=question,
            answer_data=answer,
            answer_audio=audio_file,
            transcribed_audio_data=None
        )
        
        queue_failed = False
        try:
            queue_response_evaluation(user_answer)
        except EvaluationQueueUnavailable:
            queue_failed = True

        serializer = SingleResponseSerializer(user_answer)
        data = serializer.data
        data["evaluation"] = {
            "queued": not queue_failed,
            "status": user_answer.evaluation_status,
            "stage": user_answer.evaluation_stage or "queued",
            "message": (
                "Answer saved, but evaluation could not be queued. Retry from admin when the queue is healthy."
                if queue_failed
                else "Evaluation queued. Poll evaluation status for results."
            ),
            "retryable": queue_failed,
        }
        return Response(data, status=status.HTTP_201_CREATED)

###starts here

class MockTestListAPIView(APIView):

    def get(self, request):
        try:
            # Fetch active mock tests
            mocktests = MockTest.objects.filter(is_active=True).order_by('-created_at')

            # Handle empty list
            if not mocktests.exists():
                return Response(
                    {
                        "message": "No mock tests found",
                        "data": []
                    },
                    status=status.HTTP_200_OK
                )

            serializer = MockTestListSerializer(mocktests, many=True)

            return Response(
                {
                    "message": "Mock tests fetched successfully",
                    "data": serializer.data
                },
                status=status.HTTP_200_OK
            )

        except DatabaseError:
            return Response(
                {
                    "error": "Database error occurred while fetching mock tests"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        except Exception as e:
            return Response(
                {
                    "error": f"Unexpected error: {str(e)}"
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class StartMockTestAPIView(APIView):
    def post(self, request):
        name = request.data.get("name")
        mocktest_id = request.data.get("mocktest_id")

        if not name or not mocktest_id:
            return Response({"error": "Name and mocktest_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mocktest = MockTest.objects.get(pk=mocktest_id)
        except MockTest.DoesNotExist:
            return Response({"error": "Mock test not found."}, status=status.HTTP_404_NOT_FOUND)

        session = UserMockTestSession.objects.create(
            name=name,
            session_id=str(uuid.uuid4()),
            mock_test=mocktest
        )

        return Response({
            "session_id": session.session_id,
            "mocktest_title": mocktest.title,
            "total_questions": Question.objects.filter(subsection__section__mock_test_sections__mock_test=mocktest).count()
        }, status=status.HTTP_201_CREATED)


class SingleQuestionPagination(PageNumberPagination):
    page_size = 1
    page_query_param = 'page'


class GetQuestionAPIView(APIView):
    def get(self, request):
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response(
                {"error": "session_id is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            session = UserMockTestSession.objects.select_related('mock_test').get(
                session_id=session_id
            )
        except UserMockTestSession.DoesNotExist:
            return Response(
                {"error": "Invalid session_id"},
                status=status.HTTP_404_NOT_FOUND
            )

        questions = (
            Question.objects.filter(
                mock_test_section__mock_test=session.mock_test
            )
            .select_related(
                'mock_test_section',
                'mock_test_section__section',
                'subsection'
            )
            .prefetch_related(
                'options',
                'sub_questions__options'
            )
            .order_by(
                'mock_test_section__order',
                'subsection__order',
                'id'
            )
        )

        paginator = SingleQuestionPagination()
        paginated_qs = paginator.paginate_queryset(questions, request)

        serializer = SingleQuestionSerializer(
            paginated_qs,
            many=True,
            context={
                'request': request,
                'session': session
            }
        )

        return paginator.get_paginated_response(serializer.data)


class UserResponseAPIView(APIView):
    def post(self, request):
        session_id = request.data.get('session_id')
        question_id = request.data.get('question_id')
        question_name = request.data.get('question_name')
        answer = request.data.get('answer')
        audio_file = request.FILES.get('answer_audio')

        if not session_id:
            return Response({"error": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = UserMockTestSession.objects.get(session_id=session_id)
            mock_test = session.mock_test

        except UserMockTestSession.DoesNotExist:
            return Response({"error": "Invalid session_id"}, status=status.HTTP_404_NOT_FOUND)

        question, question_error = get_session_question(
            mock_test,
            question_id=question_id,
            question_name=question_name,
        )

        if question_error == "not_found":
            return Response({"error": "Invalid question"}, status=status.HTTP_404_NOT_FOUND)
        if question_error == "invalid_id":
            return Response({"error": "question_id must be a valid integer"}, status=status.HTTP_400_BAD_REQUEST)
        if question_error == "missing":
            return Response({"error": "question_id or question_name is required"}, status=status.HTTP_400_BAD_REQUEST)
        if question_error == "duplicate":
            return Response(
                {"error": "Duplicate question_name in this mock test. Use unique question names."},
                status=status.HTTP_409_CONFLICT,
            )

        existing_response = UserResponse.objects.filter(
            user_session=session,
            question=question,
        ).first()
        if existing_response:
            return Response(
                {
                    "error": "Response already submitted for this session and question.",
                    "response_id": existing_response.id,
                    "evaluation_status": existing_response.evaluation_status,
                },
                status=status.HTTP_409_CONFLICT,
            )

                    
        user_answer = UserResponse.objects.create(
            user_session=session,
            question=question,
            mock_test=mock_test,
            answer_data=answer,
            answer_audio=audio_file,
            transcribed_audio_data=None
        )
        
        queue_failed = False
        try:
            queue_response_evaluation(user_answer)
        except EvaluationQueueUnavailable:
            queue_failed = True

        serializer = UserResponseSerializer(user_answer)
        data = serializer.data
        data["evaluation"] = {
            "queued": not queue_failed,
            "status": user_answer.evaluation_status,
            "stage": user_answer.evaluation_stage or "queued",
            "message": (
                "Answer saved, but evaluation could not be queued. Retry from admin when the queue is healthy."
                if queue_failed
                else "Evaluation queued. Poll session evaluation status for results."
            ),
            "retryable": queue_failed,
        }
        return Response(data, status=status.HTTP_201_CREATED)
    
class APIListingQuestions(APIView):
    """
    Fetch questions one by one with pagination,
    supports:
    - normal flow across sections
    - timer-based section skipping
    - empty section handling
    """

    def get(self, request):

        session_id = request.query_params.get('session_id')
        skip_section = request.headers.get('timer-exceeded', 'false').lower() == 'true'

        if not session_id:
            return Response({"error": "session_id is required"}, status=400)

        try:
            session = UserMockTestSession.objects.select_related(
                'mock_test', 'current_mocktest_section'
            ).get(session_id=session_id)
        except UserMockTestSession.DoesNotExist:
            return Response({"error": "Invalid session_id"}, status=404)

        sections = MockTestSection.objects.filter(
            mock_test=session.mock_test
        ).order_by('order')

        current_section = session.current_mocktest_section

        # ✅ INITIAL SETUP
        if not current_section:
            current_section = sections.first()
            session.current_mocktest_section = current_section
            session.save(update_fields=['current_mocktest_section'])

        # ✅ TIMER SKIP (STRICT — overrides page)
        if skip_section:
            request._request.GET = request.GET.copy()
            request._request.GET.pop('page', None)

            next_section = sections.filter(order__gt=current_section.order).first()

            if not next_section:
                return Response({"message": "All sections completed"}, status=200)

            current_section = next_section
            session.current_mocktest_section = current_section
            session.save(update_fields=['current_mocktest_section'])

        # ✅ GLOBAL QUERYSET (continuous flow)
        questions = Question.objects.filter(
            mock_test_section__mock_test=session.mock_test
        ).select_related(
            'subsection',
            'subsection__section',
            'mock_test_section'
        ).prefetch_related(
            'options',
            'sub_questions__options'
        ).order_by(
            'mock_test_section__order',
            'subsection__order',
            'id'
        )

        paginator = SingleQuestionPagination()

        # ✅ FORCE START POSITION (skip OR first load)
        if skip_section or 'page' not in request.GET:

            first_q = Question.objects.filter(
                mock_test_section=current_section
            ).order_by('subsection__order', 'id').first()

            # 🔥 HANDLE EMPTY SECTIONS
            while not first_q:
                next_section = sections.filter(order__gt=current_section.order).first()

                if not next_section:
                    return Response({"message": "All sections completed"}, status=200)

                current_section = next_section
                session.current_mocktest_section = current_section
                session.save(update_fields=['current_mocktest_section'])

                first_q = Question.objects.filter(
                    mock_test_section=current_section
                ).order_by('subsection__order', 'id').first()

            # ✅ FIND PAGE INDEX
            all_ids = list(questions.values_list('id', flat=True))

            if first_q.id in all_ids:
                start_index = all_ids.index(first_q.id)

                page_size = paginator.page_size or 1
                page_number = (start_index // page_size) + 1

                request._request.GET = request.GET.copy()
                request._request.GET['page'] = str(page_number)

        # ✅ PAGINATE
        paginated_qs = paginator.paginate_queryset(questions, request)

        if not paginated_qs:
            return Response({"message": "All sections completed"}, status=200)

        serializer = SingleQuestionSerializer(
            paginated_qs, many=True, context={'request': request}
        )

        response = paginator.get_paginated_response(serializer.data)

        # ✅ SYNC SECTION DURING NORMAL FLOW
        current_question = paginated_qs[0] if paginated_qs else None

        if current_question:
            question_section = current_question.mock_test_section

            if session.current_mocktest_section_id != question_section.id:
                session.current_mocktest_section = question_section
                session.save(update_fields=['current_mocktest_section'])

        return response
