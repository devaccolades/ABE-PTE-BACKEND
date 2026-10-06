TEMPLATE_SOURCE = "Expert evaluator - Universal templates PTE.docx"


EXPERT_ANSWER_TEMPLATES = (
    {
        "name": "Universal Describe Image",
        "answer_type": "describe_image",
        "version": "1",
        "source": TEMPLATE_SOURCE,
        "template_text": (
            "The given image gives information regarding [[image heading]]. "
            "It is evident from the image that the highest maximum element from "
            "the picture is [[highest item]] for [[highest value]], whereas the "
            "lowest minimum element from the picture is [[lowest item]] for "
            "[[lowest value]]. All the details are represented in an organised "
            "manner which is easy for the viewer to comprehend and analyse. "
            "Moreover, it helps us understand the purpose of presentation very "
            "clearly. Overall, it is an informative image and can be used for "
            "future reference."
        ),
        "minimum_match_ratio": 0.60,
        "maximum_original_words": 24,
        "minimum_matched_words": 35,
        "minimum_match_blocks": 3,
    },
    {
        "name": "Universal Retell Lecture",
        "answer_type": "retell_lecture",
        "version": "1",
        "source": TEMPLATE_SOURCE,
        "template_text": (
            "The speaker provided a brief information about [[lecture topic]]. "
            "Firstly, he utilised a significant amount of time dealing on several "
            "key topics such as [[key topics]]. To recap his detailed analysis, he "
            "mentioned [[analysis]]. He talked about [[detail]]. He highlighted "
            "some other facts too about the given topic. Finally, he suggested "
            "that [[suggestion]]. Overall the lecture was entirely clear and can "
            "be used as a specific reference for the same learning objective."
        ),
        "minimum_match_ratio": 0.58,
        "maximum_original_words": 30,
        "minimum_matched_words": 32,
        "minimum_match_blocks": 3,
    },
    {
        "name": "Universal Summarise Group Discussion",
        "answer_type": "summarise_group_discussion",
        "version": "1",
        "source": TEMPLATE_SOURCE,
        "template_text": (
            "The group discussion was mainly about [[topic]], and the three "
            "speakers presented their views and opinions on this particular "
            "subject. The first speaker mainly talked about [[point 1]]. According "
            "to the speaker, [[detail]] plays a very important role, which is an "
            "important aspect of the topic. The speaker also mentioned [[detail]]. "
            "Furthermore, this point can be connected with [[detail]], which makes "
            "the discussion more significant. Therefore, the first speaker's main "
            "point was clear and easy to understand. Moving on to the second "
            "speaker, the discussion focused on [[point 2]]. The speaker explained "
            "[[detail]], and this was presented as an important consideration. In "
            "addition, the speaker mentioned [[detail]] in relation to the topic. "
            "This perspective suggests that the speaker had a strong point of "
            "view, and they believed that the topic can have a great impact. "
            "Overall, the second speaker emphasized the importance of [[detail]]. "
            "Finally, the third speaker discussed [[point 3]] and provided another "
            "perspective on the topic. The speaker pointed out the validity of "
            "[[detail]], which is particularly relevant to the discussion. The "
            "speaker further mentioned [[detail]] and explained its inevitability "
            "in the discussion of the given topic. Taking all these points into "
            "consideration, the discussion presented different views on [[topic]], "
            "including [[point 1]], [[point 2]], and [[point 3]]. Overall, the "
            "speakers highlighted their own views and opinions, showing that "
            "[[topic]] has several important aspects that should be considered "
            "carefully."
        ),
        "minimum_match_ratio": 0.62,
        "maximum_original_words": 55,
        "minimum_matched_words": 80,
        "minimum_match_blocks": 5,
    },
    {
        "name": "Universal Respond to a Situation",
        "answer_type": "respond_to_a_situation",
        "version": "1",
        "source": TEMPLATE_SOURCE,
        "template_text": (
            "Good day to you [[person]], how are you doing today? I guess this is "
            "a good time to talk to you and hope you would not mind. I wanted to "
            "discuss with you [[topic]]. We know this is very important and needs "
            "to be thought over seriously. We also need to think about [[detail]] "
            "when we do this. I am open to all your suggestions, which I am sure "
            "you may have regarding this topic. Thank you for understanding and "
            "listening to me."
        ),
        "minimum_match_ratio": 0.60,
        "maximum_original_words": 24,
        "minimum_matched_words": 35,
        "minimum_match_blocks": 3,
    },
)
