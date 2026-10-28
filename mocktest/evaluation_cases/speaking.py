from functools import partial

from .schema import EvaluationCase


# Spoken cases submit a transcript only, so delivery traits are not asserted.
read_aloud = partial(EvaluationCase, task="read_aloud", question_id=1,
                     question_name="Passage 1: Technology and Society")
repeat = partial(EvaluationCase, task="repeat_sentence", question_id=6, question_name="RS6452-1")
# Needs the question image in MEDIA_ROOT; skipped when the export was made with --skip-media.
describe = partial(EvaluationCase, task="describe_image", question_id=7, question_name="DI6452-1")
retell = partial(EvaluationCase, task="retell_lecture", question_id=8, question_name="RL6452-1")
short_answer = partial(EvaluationCase, task="answer_short_question", question_id=9, question_name="ASQ6452-1")
situation = partial(EvaluationCase, task="respond_to_a_situation", question_id=15,
                    question_name="RTAS - Q1 - ATHIRA")
# The physical-education discussion from trainer case SGD-008.
discussion = partial(EvaluationCase, task="summarise_group_discussion", question_id=680,
                     question_name="BB-SGD 1")

PASSAGE = (
    "Technology has significantly transformed the way we live and communicate. From smartphones "
    "to artificial intelligence, modern tools have improved efficiency and convenience. However, "
    "while technology connects people globally, it also raises concerns about privacy, screen "
    "addiction, and social isolation. Striking a balance between innovation and human well-being "
    "is now more important than ever."
)

CASES = [
    read_aloud(
        id="ra-complete", label="whole passage read",
        answer=PASSAGE,
        expect={"traits": {"content": (5, 6)}},
    ),
    read_aloud(
        id="ra-first-half", label="stops after the second sentence",
        answer=PASSAGE.split(" However,")[0],
        expect={"traits": {"content": (1, 4)}},
    ),
    read_aloud(
        id="ra-unrelated", label="reads something else",
        answer="The weather today is sunny and warm, so many families are going to the beach to swim and play.",
        expect={"zero": True},
    ),
    repeat(
        id="rs-exact", label="sentence repeated exactly",
        answer="That criticism will come later in your report card.",
        expect={"traits": {"content": (3, 3)}},
    ),
    repeat(
        id="rs-partial", label="about half the words",
        answer="That criticism will come later.",
        expect={"traits": {"content": (1, 2)}},
    ),
    repeat(
        id="rs-unrelated", label="different sentence",
        answer="The library closes early on Sundays.",
        expect={"zero": True},
    ),
    describe(
        id="di-good", label="accurate description of the flow chart",
        answer="This flow chart shows how a taxi service works. Customers can book by phone, where an operator handles the request, or online through a desktop workstation. Both types of booking go to a central taxi service server, which coordinates everything and then sends the trip details to drivers of different vehicles, such as sedans and vans. Overall, it shows how phone and online bookings are combined to dispatch taxis efficiently.",
        expect={"traits": {"content": (4, 6)}},
    ),
    describe(
        id="di-template", label="generic describe-image template", trainer_ref="DI-004",
        answer="This image shows some important information. There are many different elements in the picture and they are connected to each other. The most important part is in the middle. Overall, the image gives a lot of useful information and it is very informative.",
        expect={"zero": True},
    ),
    retell(
        id="rl-good", label="faithful retell with fillers",
        answer="Um, so the speaker talks about how private cars affected city planning. In the middle of the 20th century cars let people move to the suburbs, so shopping moved away from downtown and many city businesses failed. But now there is a trend back to urban living because people want to avoid, uh, heavy commuter traffic. The speaker says we need a multi-dimensional approach, looking at social, environmental and economic factors, to plan future cities.",
        expect={"no_override": True, "traits": {"content": (4, 6)}},
    ),
    retell(
        id="rl-unpunctuated", label="faithful but lowercase with no punctuation",
        answer="so the lecture is about cars and cities um in the fifties cars let people live in suburbs and shopping moved out of downtown so city shops closed but now people are coming back to live in cities because commuting traffic is so bad and the speaker said we should think about social environmental and economic things together when we plan cities in the future",
        expect={"no_override": True, "traits": {"content": (4, 6)}},
    ),
    retell(
        id="rl-partial", label="one idea only", trainer_ref="RL-003",
        answer="The speaker talked about cars. Cars made people move to the suburbs. That's all I remember from the lecture.",
        expect={"traits": {"content": (0, 3)}},
    ),
    retell(
        id="rl-off-topic", label="fluent but about a different lecture", trainer_ref="RL-005",
        answer="The lecture was about the importance of sleep for students. The speaker explained that teenagers need around nine hours of sleep, but most of them sleep much less because of homework and phones. This affects their memory and mood, so schools should start later in the morning.",
        expect={"zero": True, "override": "source_fidelity_failed"},
    ),
    retell(
        id="rl-template", label="generic retell template", trainer_ref="RL-004",
        answer="The speaker was talking about a very important topic. He mentioned many key points and gave several examples to explain his ideas. He also talked about the advantages and disadvantages. In conclusion, the lecture was very informative and useful for everyone.",
        expect={"zero": True},
    ),
    retell(
        id="rl-keywords", label="list of keywords",
        answer="Cars, city, suburbs, shopping, downtown, business, traffic, urban, planning, economic, environmental.",
        expect={"traits": {"content": (0, 2)}},
    ),
    short_answer(
        id="asq-correct", label="correct answer in a sentence",
        answer="It is called a fiscal year.",
        expect={"ratio": (1, 1)},
    ),
    short_answer(
        id="asq-wrong", label="wrong answer",
        answer="A budget.",
        expect={"zero": True},
    ),
    situation(
        id="rts-good", label="polite and complete", trainer_ref="RTS-003",
        answer="Hi Sam, it's me. I'm really sorry, but I'm going to be late for our study group at the library. I just got an urgent call from my family and I need to sort it out first. Please go ahead and start revising without me. I should be there in about half an hour, and if you could share any notes from the beginning, that would be really helpful. Thanks for understanding.",
        expect={"no_override": True, "traits": {"content": (5, 6)}},
    ),
    situation(
        id="rts-brief", label="very brief and informal", trainer_ref="RTS-001",
        answer="Hey, I'm gonna be late, family thing. Start without me.",
        expect={"traits": {"content": (0, 3)}},
        known_issue="Trainer reports this is over-awarded; the model gives 4/6. Calibration not yet agreed.",
    ),
    situation(
        id="rts-template", label="generic polite template", trainer_ref="RTS-008",
        answer="Hello, I am calling to discuss an important matter with you. I would like to inform you about the current situation and kindly request your consideration. I hope you can understand my position. Thank you very much for your time, understanding and cooperation.",
        expect={"zero": True},
        known_issue="Scores content 1/6 and keeps delivery marks; the trainer accepted zero for this pattern.",
    ),
    situation(
        id="rts-repeats-situation", label="reads the situation back", trainer_ref="RTS-009",
        answer="You are on your way to a group meeting in the library to prepare for an upcoming exam. However, you just received an urgent phone call from a family member and need to deal with it before joining the group.",
        expect={"zero": True, "override": "copied_question_answer"},
    ),
    situation(
        id="rts-off-topic", label="talks about something else",
        answer="Hi, I wanted to ask if you have seen the new movie at the cinema. I heard it is really good and I was thinking we could go this weekend if you are free. Let me know what time works for you.",
        expect={"zero": True},
    ),
    discussion(
        id="sgd-good", label="faithful summary of all three speakers", trainer_ref="SGD-001",
        answer="The speakers discussed whether physical education should be compulsory at university. The first speaker opposed it, saying PE is stressful, time-consuming and unfair to students who are not athletic or have health problems, and that academic courses should come first. The second speaker supported it because exercise improves health, concentration and sleep and builds good habits. The third speaker partly agreed with both and suggested flexible options like yoga, hiking or dance. In the end, they all agreed that more variety would make PE better.",
        expect={"no_override": True, "traits": {"content": (4, 6)}},
    ),
    discussion(
        id="sgd-unrelated-pets", label="fluent story about pets", trainer_ref="SGD-008",
        answer="The speakers were talking about their pets. The first speaker said that dogs are the best pets because they are loyal and friendly and they help people feel less lonely. The second speaker preferred cats because they are independent and easy to look after. The third speaker said that both are good but people should adopt pets from shelters. Finally they agreed that pets make people happy.",
        expect={"zero": True, "override": "source_fidelity_failed"},
    ),
    discussion(
        id="sgd-positions-swapped", label="right topic, speaker positions reversed",
        answer="The speakers discussed compulsory physical education at university. The first speaker strongly supported mandatory PE because it improves health and sleep. The second speaker opposed it, arguing it is stressful and unfair for students who are not athletic. The third speaker agreed completely with the first speaker and said the current system works well and should not change.",
        expect={"traits": {"content": (0, 2)}},
    ),
    discussion(
        id="sgd-speaker-template", label="speaker-frame template with no content", trainer_ref="SGD-002",
        answer="The speakers were discussing an interesting topic. The first speaker gave his opinion and explained his reasons. The second speaker disagreed with the first speaker and gave another opinion. The third speaker partially agreed with both speakers. Finally, all the speakers reached a conclusion about the topic.",
        expect={"zero": True},
    ),
    discussion(
        id="sgd-one-speaker", label="covers the first speaker only",
        answer="The speakers talked about physical education in university. The first speaker did not like compulsory PE because it was stressful and took too much time, and he thought academic subjects were more important.",
        expect={"traits": {"content": (1, 3)}},
    ),
]
