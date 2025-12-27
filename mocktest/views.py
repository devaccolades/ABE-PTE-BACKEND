import os
import uuid
import tempfile
from urllib.parse import urlencode
from django.db import DatabaseError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from celery import chain
from .tasks import transcribe_task,evaluate_user_response
from .models import Question, MockTest, MockTestSection, UserResponse, UserMockTestSession, SubQuestion,Section,SubSection
from .serializers import UserMockTestSession,SingleQuestionSerializer,UserResponseSerializer,MockTestListSerializer
from .services.transcription import transcribe_and_analyse
from django.shortcuts import get_object_or_404

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

# class GetQuestionAPIView(APIView):
#     def get(self, request):
#         session_id = request.query_params.get('session_id')
#         if not session_id:
#             return Response({"error": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             session = UserMockTestSession.objects.select_related('mock_test').get(session_id=session_id)
#         except UserMockTestSession.DoesNotExist:
#             return Response({"error": "Invalid session_id"}, status=status.HTTP_404_NOT_FOUND)

#         section_ids = MockTestSection.objects.filter(
#             mock_test=session.mock_test
#         ).values_list('section_id', flat=True)

#         # Order questions properly
#         questions = (
#             Question.objects.filter(subsection__section_id__in=section_ids)
#             .select_related('subsection', 'subsection__section',)
#             .prefetch_related('options', 'sub_questions__options')
#             .order_by(
#                 'subsection__section__mock_test_sections__order',
#                 'subsection__order',
#                 'id'
#             )
#         )

#         paginator = SingleQuestionPagination()
#         paginated_qs = paginator.paginate_queryset(questions, request)
#         serializer = SingleQuestionSerializer(paginated_qs, many=True, context={'request': request})

#         return paginator.get_paginated_response(serializer.data)

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
        question_name = request.data.get('question_name')
        answer = request.data.get('answer')
        audio_file = request.FILES.get('answer_audio')

        if not session_id:
            return Response({"error": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            session = UserMockTestSession.objects.get(session_id=session_id)
            mock_test = session.mock_test
            question = Question.objects.get(name=question_name)
            sub_questions = SubQuestion.objects.filter(question=question)

        except UserMockTestSession.DoesNotExist:
            return Response({"error": "Invalid session_id"}, status=status.HTTP_404_NOT_FOUND)
        except Question.DoesNotExist:
            return Response({"error": "Invalid question_name"}, status=status.HTTP_404_NOT_FOUND)


        # if audio_file:
            
        #     temp_input_path = f"/tmp/{uuid.uuid4()}_input_audio"
        #     temp_output_path = f"/tmp/{uuid.uuid4()}_audio.wav"


        #     with open(temp_input_path, "wb") as temp:
        #         for chunk in audio_file.chunks():
        #             temp.write(chunk)
                    

        user_answer = UserResponse.objects.create(
            user_session=session,
            question=question,
            mock_test=mock_test,
            answer_data=answer,
            answer_audio=audio_file,
            transcribed_audio_data=None
        )
        
        if audio_file:
            chain(
                # transcribe_task.s(user_answer.id, temp_path),
                transcribe_task.s(user_answer.id),
                evaluate_user_response.si(user_answer.id, question.id)
            ).delay()

        else:
            evaluate_user_response.delay(user_answer.id, question.id)

        serializer = UserResponseSerializer(user_answer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class APIListingQuestions(APIView):
    """
    Fetch questions one by one with pagination,
    skipping sections whose timer has expired.
    """

    def get(self, request):

        session_id = request.query_params.get('session_id')
        skip_section = request.headers.get('timer-exceeded', 'false').lower() == 'true'

        if not session_id:
            return Response({"error": "session_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        # Load session
        try:
            session = UserMockTestSession.objects.select_related(
                'mock_test', 'current_mocktest_section'
            ).get(session_id=session_id)
        except UserMockTestSession.DoesNotExist:
            return Response({"error": "Invalid session_id"}, status=status.HTTP_404_NOT_FOUND)

        # All sections of this mock test
        mocktest_sections = MockTestSection.objects.filter(
            mock_test=session.mock_test
        ).order_by('order')

        # Find current section
        current_section = session.current_mocktest_section
        if not current_section:
            current_section = mocktest_sections.first()
            session.current_mocktest_section = current_section
            session.save(update_fields=['current_mocktest_section'])

        # Handle timer exceeded → move to next section
        if skip_section:
            next_section = mocktest_sections.filter(order__gt=current_section.order).first()
            if next_section:
                current_section = next_section
                session.current_mocktest_section = current_section
                session.save(update_fields=['current_mocktest_section'])
            else:
                return Response({"message": "All sections completed"}, status=status.HTTP_200_OK)

        # 🔥 GLOBAL QUESTION QUERYSET (covers ALL sections)
        questions = Question.objects.filter(
            subsection__section__in=mocktest_sections.values_list('section', flat=True)
        ).select_related(
            'subsection', 'subsection__section'
        ).prefetch_related(
            'options', 'sub_questions__options'
        ).order_by(
        'subsection__section__mock_test_sections__order',
        'subsection__order',
        'id')


        # 🔥 If timer exceeded → jump paginator to next section start
        if skip_section:
            first_question_in_next_section = Question.objects.filter(
                subsection__section=current_section.section
            ).order_by('subsection__order', 'id').first()

            if first_question_in_next_section:
                all_ids = list(questions.values_list('id', flat=True))
                start_index = all_ids.index(first_question_in_next_section.id)

                # Force paginator to start from correct page number
                request._request.GET._mutable = True
                request._request.GET['page'] = str(start_index + 1)
                request._request.GET._mutable = False

        # PAGINATE OVER GLOBAL QUERYSET
        paginator = SingleQuestionPagination()
        paginated_qs = paginator.paginate_queryset(questions, request)
        serializer = SingleQuestionSerializer(paginated_qs, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)
