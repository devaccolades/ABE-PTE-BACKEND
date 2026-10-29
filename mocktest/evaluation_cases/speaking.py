"""Speaking cases. Expectations follow the band descriptors in Pearson's PTE Academic
Test Taker Score Guide (2025), which the question-bank rubrics reproduce.

Spoken cases submit a transcript only, so delivery traits are not asserted. A content
score of 0 gates the whole answer (no pronunciation or fluency points), as in PTE.
"""

from functools import partial

from .schema import EvaluationCase


read_aloud = partial(EvaluationCase, task="read_aloud", question_id=1,
                     question_name="Passage 1: Technology and Society")
read_aloud_2 = partial(EvaluationCase, task="read_aloud", question_id=23, question_name="RA Q1- BB")
# "That criticism will come later in your report card" (9 words)
repeat = partial(EvaluationCase, task="repeat_sentence", question_id=6, question_name="RS6452-1")
# "At any given time, the laboratory allows a maximum of four individuals inside." (13 words)
repeat_2 = partial(EvaluationCase, task="repeat_sentence", question_id=50, question_name="RS Q2 -BB")
# Image cases need the question image in MEDIA_ROOT; otherwise they are skipped.
describe = partial(EvaluationCase, task="describe_image", question_id=7, question_name="DI6452-1")
describe_2 = partial(EvaluationCase, task="describe_image", question_id=56, question_name="DI Q2 - BB")
retell = partial(EvaluationCase, task="retell_lecture", question_id=8, question_name="RL6452-1")
retell_2 = partial(EvaluationCase, task="retell_lecture", question_id=62, question_name="RL Q2 - BB")
short_answer = partial(EvaluationCase, task="answer_short_question", question_id=9, question_name="ASQ6452-1")
situation = partial(EvaluationCase, task="respond_to_a_situation", question_id=15,
                    question_name="RTAS - Q1 - ATHIRA")
situation_2 = partial(EvaluationCase, task="respond_to_a_situation", question_id=72, question_name="RTS 2 - BB")
# The physical-education discussion from trainer case SGD-008.
discussion = partial(EvaluationCase, task="summarise_group_discussion", question_id=680,
                     question_name="BB-SGD 1")
discussion_2 = partial(EvaluationCase, task="summarise_group_discussion", question_id=67,
                       question_name="SGD Q1 - BB")

# 53 words in four sentences of 10, 12, 17 and 14 words. Read Aloud content bands are
# the share of prompt words reproduced: 15/30/45/60/75/90% for bands 1-6.
PASSAGE = (
    "Technology has significantly transformed the way we live and communicate. From smartphones "
    "to artificial intelligence, modern tools have improved efficiency and convenience. However, "
    "while technology connects people globally, it also raises concerns about privacy, screen "
    "addiction, and social isolation. Striking a balance between innovation and human well-being "
    "is now more important than ever."
)
SENTENCES = PASSAGE.split(". ")
PASSAGE_2 = (
    "Modern technology changed a lot from what we saw in the last decade or the past century. "
    "New machines and gadgets have been invented to make jobs easier like never before. From the "
    "smallest tailor machine to the fastest car in the world, all got automated reducing the "
    "manual actions required to the least."
)
TEMPLATE_DESCRIBE = (
    "This image shows some important information. There are many different elements in the picture "
    "and they are connected to each other. The most important part is in the middle. Overall, the "
    "image gives a lot of useful information and it is very informative."
)
TEMPLATE_RETELL = (
    "The speaker was talking about a very important topic. He mentioned many key points and gave "
    "several examples to explain his ideas. He also talked about the advantages and disadvantages. "
    "In conclusion, the lecture was very informative and useful for everyone."
)

CASES = [
    # Read Aloud: errors are replacements, omissions and insertions; hesitations are ignored.
    read_aloud(id="ra-complete", label="whole passage (100%)", answer=PASSAGE,
               expect={"traits": {"content": (5, 6)}}),
    read_aloud(
        id="ra-fillers", label="whole passage with um/uh hesitations (ignored by PTE)",
        answer=PASSAGE.replace("transformed", "um, transformed").replace("However,", "uh, However,"),
        expect={"traits": {"content": (5, 6)}},
    ),
    read_aloud(
        id="ra-two-replacements", label="two words replaced (96%)",
        answer=PASSAGE.replace("significantly", "greatly").replace("convenience", "comfort"),
        expect={"traits": {"content": (5, 6)}},
    ),
    read_aloud(
        id="ra-skips-a-sentence", label="third sentence skipped (68%, band 4)",
        answer=". ".join([SENTENCES[0], SENTENCES[1], SENTENCES[3]]),
        expect={"traits": {"content": (3, 5)}},
    ),
    read_aloud(
        id="ra-first-half", label="first two sentences only (42%, band 2)",
        answer=". ".join(SENTENCES[:2]) + ".",
        expect={"traits": {"content": (1, 3)}},
    ),
    read_aloud(
        id="ra-first-sentence", label="first sentence only (19%, band 1)",
        answer=SENTENCES[0] + ".",
        expect={"traits": {"content": (0, 2)}},
    ),
    read_aloud(
        id="ra-unrelated", label="reads something else",
        answer="The weather today is sunny and warm, so many families are going to the beach to swim and play.",
        expect={"zero": True},
    ),
    read_aloud_2(id="ra2-complete", label="whole passage", answer=PASSAGE_2,
                 expect={"traits": {"content": (5, 6)}}),
    read_aloud_2(
        id="ra2-first-sentence", label="first sentence only (about 30%)",
        answer=PASSAGE_2.split(". ")[0] + ".",
        expect={"traits": {"content": (1, 3)}},
    ),

    # Repeat Sentence: 3 all words in sequence; 2 at least 50%; 1 less than 50%; 0 almost nothing.
    repeat(id="rs-exact", label="sentence repeated exactly",
           answer="That criticism will come later in your report card.",
           expect={"traits": {"content": (3, 3)}}),
    repeat(id="rs-hesitation", label="exact with a hesitation (ignored by PTE)",
           answer="That criticism, um, will come later in your report card.",
           expect={"traits": {"content": (3, 3)}}),
    repeat(id="rs-one-omission", label="one word omitted (band 2)",
           answer="That criticism will come later in report card.",
           expect={"traits": {"content": (2, 2)}}),
    repeat(id="rs-one-replacement", label="one word replaced (band 2)",
           answer="That feedback will come later in your report card.",
           expect={"traits": {"content": (2, 2)}}),
    repeat(id="rs-partial", label="first five of nine words (band 2)",
           answer="That criticism will come later.",
           expect={"traits": {"content": (1, 2)}}),
    repeat(id="rs-few-words", label="three scattered words (band 1)",
           answer="Criticism later report.",
           expect={"traits": {"content": (1, 1)}}),
    repeat(id="rs-reordered", label="all words but clauses reordered",
           answer="In your report card that criticism will come later.",
           expect={"traits": {"content": (1, 2)}}),
    repeat(id="rs-unrelated", label="different sentence", answer="The library closes early on Sundays.",
           expect={"zero": True}),
    repeat_2(id="rs2-exact", label="13-word sentence repeated exactly",
             answer="At any given time, the laboratory allows a maximum of four individuals inside.",
             expect={"traits": {"content": (3, 3)}}),
    repeat_2(id="rs2-half", label="first seven of thirteen words (band 2)",
             answer="At any given time, the laboratory allows.",
             expect={"traits": {"content": (1, 2)}}),
    repeat_2(id="rs2-gist-only", label="paraphrased gist, few prompt words",
             answer="Only four people can be in the lab.",
             expect={"traits": {"content": (0, 1)}}),

    # Describe Image: 6 full with relationships ... 1 a list of points; memorised material is irrelevant (0).
    describe(
        id="di-good", label="accurate flow-chart description with relationships",
        answer="This flow chart shows how a taxi service works. Customers can book by phone, where an operator handles the request, or online through a desktop workstation. Both types of booking go to a central taxi service server, which coordinates everything and then sends the trip details to drivers of different vehicles, such as sedans and vans. Overall, it shows how phone and online bookings are combined to dispatch taxis efficiently.",
        expect={"traits": {"content": (4, 6)}},
    ),
    describe(
        id="di-superficial", label="superficial description (band 2-3)",
        answer="This picture is about taxis. There are some phones and a computer and some cars. People can book a taxi. It is a picture with arrows.",
        expect={"traits": {"content": (1, 3)}},
    ),
    describe(
        id="di-word-list", label="list of labels without description (band 1)",
        answer="Taxi. Phone. Online. Operator. Server. Drivers. Vans.",
        expect={"traits": {"content": (0, 1)}},
    ),
    describe(
        id="di-template", label="generic describe-image template", trainer_ref="DI-004",
        answer=TEMPLATE_DESCRIBE, expect={"zero": True},
        known_issue="Often scores content 1/6 instead of zero, so generic templates keep some marks.",
    ),
    describe(
        id="di-wrong-image", label="fluent description of a different chart",
        answer="This pie chart shows energy sources in Germany in 2020. Coal accounts for about forty percent, followed by wind at twenty-five percent and solar at fifteen percent. Nuclear and gas make up the rest. Overall, fossil fuels still dominate the energy mix.",
        expect={"zero": True},
    ),
    describe_2(
        id="di2-good", label="bar chart with correct figures and conclusion",
        answer="The bar chart compares how people travelled in Sydney in 2004. By far the most popular choice was private vehicles, at seventy-two percent of trips. Walking came second with seventeen percent, while public transport such as trains, buses and ferries made up only ten percent, and other modes just two percent. Overall, people in Sydney relied heavily on their own cars compared with every other option.",
        expect={"traits": {"content": (5, 6)}},
    ),
    describe_2(
        id="di2-wrong-figures", label="right chart, key figures swapped",
        answer="The bar chart shows transport in Sydney in 2004. Walking was the most popular mode at seventy-two percent, followed by cars at seventeen percent. Public transport was about ten percent and other modes two percent. So most people in Sydney walk.",
        expect={"traits": {"content": (1, 4)}},
        known_issue="Swapped figures still score content 5/6. Not tightened by decision.",
    ),
    describe_2(id="di2-template", label="generic describe-image template", answer=TEMPLATE_DESCRIBE,
               expect={"zero": True},
               known_issue="Often scores content 1/6 instead of zero, so generic templates keep some marks."),

    # Retell Lecture: 6 full paraphrase ... 1 isolated words; memorised material is irrelevant (0).
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
        id="rl-template-wrapped", label="template opening and closing around real content",
        answer="The speaker was talking about a very important topic, which is how private cars changed city planning. He explained that after cars became common, people moved to the suburbs and shopping left downtown, so many city businesses failed. He also said that people are now returning to cities to avoid commuting traffic. In conclusion, the lecture was very informative and suggested a multi-dimensional approach to future planning.",
        expect={"no_override": True, "traits": {"content": (3, 6)}},
    ),
    retell(
        id="rl-inaccurate", label="right topic, key claims wrong (band 2)",
        answer="The lecture was about cars and cities. The speaker said cars made downtown shopping grow very fast and that nobody lives in the suburbs anymore. He also said traffic is not a problem today, so cities do not need any planning.",
        expect={"traits": {"content": (0, 2)}},
    ),
    retell(
        id="rl-partial", label="one idea only", trainer_ref="RL-003",
        answer="The speaker talked about cars. Cars made people move to the suburbs. That's all I remember from the lecture.",
        expect={"traits": {"content": (0, 3)}},
    ),
    retell(
        id="rl-keywords", label="list of keywords (band 1)",
        answer="Cars, city, suburbs, shopping, downtown, business, traffic, urban, planning, economic, environmental.",
        expect={"traits": {"content": (0, 2)}},
        known_issue="A bare keyword list occasionally scores content 3/6.",
    ),
    retell(
        id="rl-off-topic", label="fluent but about a different lecture", trainer_ref="RL-005",
        answer="The lecture was about the importance of sleep for students. The speaker explained that teenagers need around nine hours of sleep, but most of them sleep much less because of homework and phones. This affects their memory and mood, so schools should start later in the morning.",
        expect={"zero": True, "override": "source_fidelity_failed"},
    ),
    retell(id="rl-template", label="generic retell template", trainer_ref="RL-004",
           answer=TEMPLATE_RETELL, expect={"zero": True}),
    retell_2(
        id="rl2-good", label="internet lecture, all main points",
        answer="The lecture is about how the internet has changed modern life. First, it made communication instant and global. Second, it improved access to education through online resources. It has also encouraged innovation and helped new businesses start. However, the speaker warned about problems like privacy, misinformation and the digital divide. Overall, the internet remains a key force shaping society.",
        expect={"no_override": True, "traits": {"content": (4, 6)}},
    ),
    retell_2(
        id="rl2-one-point", label="internet lecture, communication only",
        answer="The speaker said the internet changed communication and now we can talk to people around the world instantly.",
        expect={"traits": {"content": (1, 3)}},
    ),
    retell_2(id="rl2-template", label="generic retell template", answer=TEMPLATE_RETELL,
             expect={"zero": True}),

    # Answer Short Question: correct/incorrect.
    short_answer(id="asq-correct", label="correct answer in a sentence",
                 answer="It is called a fiscal year.", expect={"ratio": (1, 1)}),
    short_answer(id="asq-wrong", label="wrong answer", answer="A budget.", expect={"zero": True}),

    # Respond to a Situation: 6 effective and persuasive ... 1 minimal goal with no elaboration.
    situation(
        id="rts-good", label="polite and complete", trainer_ref="RTS-003",
        answer="Hi Sam, it's me. I'm really sorry, but I'm going to be late for our study group at the library. I just got an urgent call from my family and I need to sort it out first. Please go ahead and start revising without me. I should be there in about half an hour, and if you could share any notes from the beginning, that would be really helpful. Thanks for understanding.",
        expect={"no_override": True, "traits": {"content": (5, 6)}},
    ),
    situation(
        id="rts-partial-goal", label="apologises and says late, but no reason or plan (band 3-4)",
        answer="Hi, sorry, I'm going to be late for the group meeting today. Sorry about that.",
        expect={"traits": {"content": (2, 4)}},
    ),
    situation(
        id="rts-brief", label="10 words, goal met with no elaboration (Pearson band 1)", trainer_ref="RTS-001",
        answer="Hey, I'm gonna be late, family thing. Start without me.",
        expect={"traits": {"content": (0, 3)}},
        known_issue="Pearson's band 1 describes exactly this; the model gives 4/6.",
    ),
    situation(
        id="rts-rude", label="goal met but situationally inappropriate tone",
        answer="Listen, I'm not coming now. Family stuff. Just do the revision yourselves and stop waiting for me, it's not my problem.",
        expect={"traits": {"content": (1, 3)}},
    ),
    situation(
        id="rts-template", label="generic polite template", trainer_ref="RTS-008",
        answer="Hello, I am calling to discuss an important matter with you. I would like to inform you about the current situation and kindly request your consideration. I hope you can understand my position. Thank you very much for your time, understanding and cooperation.",
        expect={"zero": True},
        known_issue="Scores content 1-2/6 and keeps delivery marks; the trainer accepted zero for this pattern.",
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
    situation_2(
        id="rts2-good", label="flatmates: polite, explains concern, proposes a fix",
        answer="Hey everyone, can I have a quick word? I've noticed my desk and stationery are often being used while I'm out. I don't mind sharing sometimes, but I've lost a few pens and notes, and I'm worried about losing more important things. Could you please ask me first before using them? Maybe we could also buy some shared stationery for the common area. Thanks, I really appreciate it.",
        expect={"no_override": True, "traits": {"content": (5, 6)}},
    ),
    situation_2(
        id="rts2-minimal", label="flatmates: one-line request (band 1)",
        answer="Please don't use my desk.",
        expect={"traits": {"content": (0, 2)}},
    ),
    situation_2(
        id="rts2-aggressive", label="flatmates: goal met with hostile tone",
        answer="Stop touching my desk and my things right now. If anything goes missing again I am calling the landlord and you will pay for it.",
        expect={"traits": {"content": (1, 4)}},
    ),
    situation_2(
        id="rts2-off-topic", label="flatmates: talks about cooking rota instead",
        answer="Hi guys, I think we should make a cooking rota so everyone cooks dinner once a week. I can start on Monday and make pasta for everybody. Let me know which day you prefer.",
        expect={"zero": True},
    ),

    # Summarize Group Discussion: 6 synthesises perspectives ... 1 isolated words; memorised is 0.
    discussion(
        id="sgd-good", label="all three speakers plus the shared conclusion", trainer_ref="SGD-001",
        answer="The speakers discussed whether physical education should be compulsory at university. The first speaker opposed it, saying PE is stressful, time-consuming and unfair to students who are not athletic or have health problems, and that academic courses should come first. The second speaker supported it because exercise improves health, concentration and sleep and builds good habits. The third speaker partly agreed with both and suggested flexible options like yoga, hiking or dance. In the end, they all agreed that more variety would make PE better.",
        expect={"no_override": True, "traits": {"content": (4, 6)}},
    ),
    discussion(
        id="sgd-no-synthesis", label="each speaker in turn, no relationship or conclusion (band 4)",
        answer="The first speaker does not like compulsory PE because it is stressful and unfair. The second speaker likes PE because it is good for health and sleep. The third speaker talked about yoga, walking clubs, hiking and dance classes.",
        expect={"traits": {"content": (2, 4)}},
    ),
    discussion(
        id="sgd-one-speaker", label="covers the first speaker only",
        answer="The speakers talked about physical education in university. The first speaker did not like compulsory PE because it was stressful and took too much time, and he thought academic subjects were more important.",
        expect={"traits": {"content": (1, 3)}},
    ),
    discussion(
        id="sgd-positions-swapped", label="right topic, speaker positions misattributed (Pearson band 1-2)",
        answer="The speakers discussed compulsory physical education at university. The first speaker strongly supported mandatory PE because it improves health and sleep. The second speaker opposed it, arguing it is stressful and unfair for students who are not athletic. The third speaker agreed completely with the first speaker and said the current system works well and should not change.",
        expect={"no_override": True, "traits": {"content": (1, 3)}},
    ),
    discussion(
        id="sgd-unrelated-pets", label="fluent story about pets", trainer_ref="SGD-008",
        answer="The speakers were talking about their pets. The first speaker said that dogs are the best pets because they are loyal and friendly and they help people feel less lonely. The second speaker preferred cats because they are independent and easy to look after. The third speaker said that both are good but people should adopt pets from shelters. Finally they agreed that pets make people happy.",
        expect={"zero": True, "override": "source_fidelity_failed"},
    ),
    discussion(
        id="sgd-speaker-template", label="speaker-frame template with no content", trainer_ref="SGD-002",
        answer="The speakers were discussing an interesting topic. The first speaker gave his opinion and explained his reasons. The second speaker disagreed with the first speaker and gave another opinion. The third speaker partially agreed with both speakers. Finally, all the speakers reached a conclusion about the topic.",
        expect={"zero": True},
    ),
    discussion_2(
        id="sgd2-good", label="group projects: all speakers and conclusion",
        answer="The students discussed how to make university group projects work better. The first speaker had a bad experience where she did most of the work, so she wants tasks divided fairly. The second speaker suggested clear roles and deadlines from the start, shared documents to track progress, and a plan for members who don't contribute. The third speaker added regular check-in meetings and project management apps. Overall, they agreed that planning, communication and teamwork make projects succeed.",
        expect={"no_override": True, "traits": {"content": (4, 6)}},
    ),
    discussion_2(
        id="sgd2-wrong-discussion", label="group projects: summarises the PE discussion instead",
        answer="The speakers discussed whether physical education should be compulsory at university. One speaker opposed it because it is stressful, another supported it for health reasons, and the third suggested flexible options like yoga and dance.",
        expect={"zero": True, "override": "source_fidelity_failed"},
    ),
]
