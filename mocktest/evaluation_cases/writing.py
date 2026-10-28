from functools import partial

from .schema import EvaluationCase


# Source: Indian Ocean passage (206 words). Rubric: form 1, content 4, grammar 2, vocabulary 2.
swt = partial(EvaluationCase, task="summarize_written_text", question_id=312, question_name="SWT6452-2")
# Prompt: "Do you agree that the modern lifestyle is too fast-paced for good mental health?"
# Rubric: form 2, content 6, grammar 2, spelling 2, vocabulary_range 2,
# general_linguistic_range 6, development_structure_coherence 6.
essay = partial(EvaluationCase, task="write_essay", question_id=669, question_name="BB-WE")

FIDELITY_QUOTES = (
    "Source fidelity rejects source quotes the model joins with '...' or writes with "
    "straight apostrophes, so faithful summaries fail after retries."
)

CASES = [
    swt(
        id="swt-good", label="faithful one-sentence summary",
        answer="The Indian Ocean, the third-largest ocean and landlocked to the north by Asia, drives monsoon patterns that shape the economies of South Asia and East Africa and has long been a vital trade crossroads that still carries much of the world's oil and gas, but rising sea temperatures and geopolitical competition over shipping lanes now make managing its environmental and strategic risks a primary concern for bordering nations.",
        expect={"no_override": True, "traits": {"content": (3, 4)}, "ratio": (0.75, 1)},
        known_issue=FIDELITY_QUOTES,
    ),
    swt(
        id="swt-partial", label="one minor idea only",
        answer="The Indian Ocean is the third-largest ocean and it has been important for trade between many countries for centuries.",
        expect={"traits": {"content": (0, 2)}},
    ),
    swt(
        id="swt-off-topic", label="fluent summary of a different subject",
        answer="Social media has changed the way young people communicate, making friendships easier to maintain online while also increasing anxiety and reducing face-to-face interaction among teenagers in many countries around the world.",
        expect={"zero": True, "override": "source_fidelity_failed"},
        known_issue="Strict Form zeroes it first, so the student is told Form failed instead of off-topic.",
    ),
    swt(
        id="swt-reversed", label="core meaning reversed", trainer_ref="SWT-003",
        answer="The Indian Ocean is a minor body of water with no influence on regional weather, it has never mattered for trade or energy transport, and neither climate change nor geopolitical competition poses any risk to the region, so bordering nations do not need to be concerned.",
        expect={"zero": True, "override": "source_fidelity_failed"},
    ),
    swt(
        id="swt-template", label="generic filler with no source content",
        answer="The passage discusses an important topic which has many aspects, and the author explains various key points in detail, highlighting significant ideas and emphasizing the importance of the issue, which is relevant to modern society and deserves careful consideration by everyone.",
        expect={"zero": True},
        known_issue="A generic template quote under 4 words rejects the whole result, so it fails instead of scoring zero.",
    ),
    swt(
        id="swt-over-75-words", label="good content, 80 words",
        answer="The Indian Ocean, which is the third-largest of the world's oceans and is landlocked to the north by the Asian continent, drives the powerful monsoon patterns that shape the agricultural and economic cycles of billions of people in South Asia and East Africa, and it has long been a vital crossroads for trade that still carries a large share of the world's oil and gas, but rising sea temperatures and geopolitical competition over its shipping lanes now threaten the region.",
        expect={"zero": True, "override": "company_strict_form"},
    ),
    swt(
        id="swt-two-sentences", label="good content, two sentences",
        answer="The Indian Ocean is the third-largest ocean and drives the monsoons that shape South Asian and East African economies. It remains a vital trade route for oil and gas, but warming seas and geopolitical competition now threaten the region.",
        expect={"zero": True, "override": "company_strict_form"},
    ),
    swt(
        id="swt-semicolon-capitals", label="one sentence, capitals after semicolons", trainer_ref="SWT-001",
        answer="The Indian Ocean is the third-largest ocean and is landlocked to the north by Asia; It drives monsoon patterns that affect billions of people in South Asia and East Africa; It has long been a crossroads for trade and still carries much of the world's oil and gas; However, warming seas and geopolitical rivalry now threaten the region.",
        expect={"zero": False},
    ),
    swt(
        id="swt-abbreviations", label="one sentence with abbreviations (i.e., S. Asia)",
        answer="The Indian Ocean, i.e. the third-largest ocean, drives the monsoons of S. Asia and E. Africa and has long served as a trade crossroads that still carries oil and gas through chokepoints like the Strait of Hormuz, but warming seas and geopolitical competition now threaten it.",
        expect={"zero": False},
    ),
    swt(
        id="swt-unanswered", label="empty submission", answer="",
        expect={"zero": True},
    ),
    essay(
        id="essay-good", label="relevant, developed, 260 words",
        answer="Many people today live at a pace that would have seemed impossible a generation ago, and I agree that this fast-paced lifestyle is harmful to mental health, although its effects can be reduced.\n\nThe first problem is constant work pressure. Smartphones and email mean that employees are expected to respond at night and on weekends, so the boundary between work and rest has almost disappeared. When people never fully switch off, stress hormones stay high, and this leads to anxiety, irritability and eventually burnout. A friend of mine who worked in a consulting firm described answering messages at midnight as normal, and she later needed months of leave to recover.\n\nSecondly, a hurried routine damages sleep and relationships. People shorten their sleep to fit in more tasks, yet poor sleep is closely linked to depression and weaker concentration. In addition, families who eat in front of screens or rarely meet in person lose the face-to-face support that protects mental wellbeing. Social media makes this worse, because users constantly compare their ordinary lives with the edited success of others.\n\nOn the other hand, the modern world also offers solutions. Flexible working hours, online therapy and mindfulness applications make it easier to look after mental health than in the past, provided people use them deliberately.\n\nIn conclusion, the speed of modern life puts serious pressure on mental health through work stress, lost sleep and weaker relationships. Nevertheless, if individuals set clear limits on technology and employers respect rest time, it is possible to enjoy the benefits of modern life without sacrificing wellbeing.",
        expect={"no_override": True, "traits": {"content": (5, 6)}, "ratio": (0.75, 1)},
    ),
    essay(
        id="essay-template", label="generic essay that fits any prompt",
        answer="In today's modern world, this issue has become increasingly important and has attracted the attention of many people. There are various opinions about this topic, and in this essay I will discuss both sides of the argument before giving my own opinion.\n\nOn the one hand, there are many advantages that should be considered. Firstly, it is undeniable that this matter has a significant impact on individuals and society as a whole. Many experts believe that it brings numerous benefits which can improve the quality of life for many people. For example, people can gain a lot from it in different aspects of their daily lives. Moreover, it plays a crucial role in the development of the modern world.\n\nOn the other hand, there are also some disadvantages that cannot be ignored. Some people argue that it may cause several problems which can negatively affect people in many ways. For instance, there are various issues that arise as a result of this situation. Furthermore, it is important to consider the long-term consequences, which may be serious if they are not addressed properly by the relevant authorities.\n\nIn conclusion, although there are both advantages and disadvantages, I believe that the benefits outweigh the drawbacks. It is essential that governments and individuals work together to find appropriate solutions to this issue so that everyone can enjoy a better future. Therefore, this topic deserves careful attention from everyone in society.",
        expect={"zero": True},
        known_issue="The template detector only flags this for review, so the essay keeps about 16/26.",
    ),
    essay(
        id="essay-generic-intro", label="template-like framing around a real argument", trainer_ref="WE-002",
        answer="In today's modern world, mental health has become increasingly important. This essay will discuss the major reasons behind this issue and explain why I agree that modern life is too fast-paced.\n\nThe main reason is the pressure of deadlines at work. Many employees are given more tasks than they can complete in normal hours, so they stay late and skip breaks. Over time, this constant rush leads to exhaustion and burnout, and some workers develop anxiety because they always feel behind.\n\nAnother reason is the lack of sleep. Because people try to fit work, study, exercise and social events into one day, they often sleep only five or six hours. Doctors warn that long-term sleep loss weakens concentration and increases the risk of depression.\n\nFurthermore, screen time and social media make people feel rushed even when they are resting. Scrolling late at night keeps the brain alert, and comparing oneself with others online makes many young people feel that they are not achieving enough. As a result, face-to-face relationships become weaker, and people have fewer friends to talk to when they are stressed.\n\nIn conclusion, deadlines, short sleep and excessive screen time show that the speed of modern life damages mental health. To protect themselves, people should set limits on working hours, keep regular sleep schedules and spend more time with family and friends without their phones. Employers and schools also have a responsibility to reduce unnecessary pressure.",
        expect={"no_override": True, "traits": {"content": (4, 6)}},
    ),
    essay(
        id="essay-under-200-words", label="good content, 121 words", trainer_ref="WE-003/WE-004",
        answer="I agree that the modern lifestyle is too fast-paced for good mental health.\n\nFirstly, work never stops. Smartphones mean that employees answer emails at night and on weekends, so they cannot rest properly. This constant pressure causes stress and burnout.\n\nSecondly, people sleep less because they try to do too many things in one day. Lack of sleep is strongly linked to anxiety and depression.\n\nFinally, social media makes people compare themselves with others, which lowers self-esteem, especially among teenagers.\n\nHowever, technology also offers online therapy and meditation apps that can help.\n\nIn conclusion, the speed of modern life harms mental health, but people can reduce the damage by setting limits on work and screen time and by protecting their sleep.",
        expect={"zero": True, "override": "company_strict_form"},
    ),
    essay(
        id="essay-off-topic", label="well written but about online shopping",
        answer="Online shopping has transformed the way people buy goods, and I believe its advantages clearly outweigh its disadvantages.\n\nThe most obvious benefit is convenience. Customers can browse thousands of products at any time of day without leaving their homes, and items are delivered directly to their door, often within a day or two. This is especially valuable for elderly people or those living in rural areas far from large shops.\n\nAnother advantage is price comparison. Websites allow shoppers to compare the prices of the same product from many sellers in seconds, which encourages competition and lowers costs. Customer reviews also help buyers avoid poor-quality products.\n\nHowever, online shopping has some drawbacks. Customers cannot touch or try products before buying, so clothes may not fit and must be returned. In addition, small local shops struggle to compete with large online retailers, and some town centres have lost their traditional character as a result. Delivery vans also add to traffic and pollution.\n\nIn conclusion, although online shopping can harm local businesses and the environment, its convenience, lower prices and wider choice make it a positive development overall. Governments should support local shops and encourage greener delivery methods so that society can enjoy its benefits while reducing its negative effects.",
        expect={"zero": True},
    ),
]
