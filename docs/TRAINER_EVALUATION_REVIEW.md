# Trainer Evaluation Review

Created: 23 October 2026
Phase: Initial report collection complete. Scoped source-fidelity implementation
authorized after read-only server inspection. Production results remain unchanged.

## Working Agreement

- Collect one question evaluation at a time, naming its assigned evaluator.
- Preserve the trainer's observations separately from the system output and our analysis.
- Compare the actual candidate response, task/source, rubric and awarded result.
- Do not assume a discrepancy is an AI, configuration, scoring or frontend bug.
- Label findings as confirmed, suspected, expected behaviour or insufficient evidence.
- Record missing evidence rather than inventing expected scores or causes.
- Do not change code, question configuration, saved results or evaluation state
  during this collection phase. Do not retry evaluations without approval.
- After collection, agree on fixes and regression cases before implementation.

## Assignments and Status

| # | Task Type | Backend Type | Assigned Evaluator | Current Status |
| --- | --- | --- | --- | --- |
| 1 | Read Aloud | `read_aloud` | Santhi | PTE.docx report received: two scenarios; original evaluation evidence pending |
| 2 | Repeat Sentence | `repeat_sentence` | Bindu | User reports it is working well; no change requested |
| 3 | Describe Image | `describe_image` | Athira | DI - Athira.docx received: five attempts with transcript/score screenshots; image/audio/IDs pending |
| 4 | Retell Lecture | `retell_lecture` | Salini | Report received: six attempts; Moderate/Template screenshots mixed; original lecture/audio/IDs pending |
| 5 | Summarize Group Discussion (SGD) | `summarise_group_discussion` | Hitha | Report received: eight attempts, six with screenshots; off-topic Content award is priority for source verification |
| 6 | Respond to a Situation (RTS) | `respond_to_a_situation` | John Sir | Report received: nine screenshot-backed cases; short-answer Content and low Fluency disputed; six results accepted by trainer |
| 7 | Summarize Written Text (SWT) | `summarize_written_text` | Anupama | Remarks.pdf received: four answers/reported results; meaning reversal awarded nonzero marks; original passage/IDs pending |
| 8 | Write Essay | `write_essay` | Anupama | Remarks.pdf received: five answers/reported results; 187/143-word answers reported above 22/28; deployment chronology pending |
| 9 | Summarize Spoken Text (SST) | `summarize_spoken_text` | Paval | Report received: five written attempts plus repeated Listening score concern; original answers/source/results pending |
| 10 | Write from Dictation (WFD) | `write_from_dictation` | Paval | Report received: one written mismatch, three correct words reportedly credited as two; exact reference/answer/results pending |

Repeat Sentence's status is trainer/user-reported, not an independent verification
of new question-level evidence in this review. Leave it unchanged unless a new
case is raised.

## Progress

- Trainer report documents received: 7 (`PTE.docx`, `DI - Athira.docx`,
  `Re-tell lecture Evaluation-Salini (1).docx`, `Hitha SGD Summary (1).docx`,
  `RTS John (1).docx`, `Remarks.pdf`, `SST and WFD .docx`).
- Task types with a report received: 9 of the 9 requested types (100%).
- Other task types awaiting a first report: 0. Initial report collection complete.
- Reported Read Aloud scenarios recorded: 2.
- Describe Image attempts recorded with visible evaluation/transcript screenshots: 5.
- Retell Lecture attempts recorded: 6; two have conflicting screenshot placement.
- SGD attempts recorded: 8; six have screenshots and two are written reports only.
- RTS cases recorded: 9, all with screenshots; three disputed and six accepted
  by the trainer. Template/stem-repetition examples visibly receive zero.
- SWT cases recorded: 4 with answer text and written result reports, no original
  evaluation screenshots. Meaning reversal is the primary concern.
- Essay cases recorded: 5 with answer text and written result reports, no original
  evaluation screenshots. Local counts verify two essays are below 200 words;
  the reported results need comparison with the active policy at evaluation time.
- SST attempts recorded: 5 written reports plus one cross-attempt contribution
  concern; no candidate answers, source audio or result screenshots supplied.
- WFD attempts recorded: 1 written report; exact reference and submitted words
  not supplied. The document calls it "Attempt 2"; no Attempt 1 was provided.
- Question-level scenarios/attempts recorded: 45 across these nine task types.
  Excludes Repeat Sentence's general pass report and SST's cross-attempt note.
- Priority source-grounding concern: SGD-008, pets response awarded Content 5/6
  for a reportedly physical-education discussion; original source/ID pending.
- Cases with the complete original question/source, recording and server result: 0.
- Grading defects independently confirmed against the original inputs: 0.
- Visible feedback-language issue recorded: 1 (unexpected Arabic word in DI-005).
- Fix implementation: Source-fidelity protection for RL/SGD/SST/SWT authorized
  and implemented locally; deployment/live-model verification pending. Other
  trainer concerns remain under investigation, not declared fixed.

Task-type coverage does not mean all questions of a type have been verified.
The number of cases needed is not yet known. Do not assign an overall fix
completion percentage until the issue list and acceptance criteria are agreed.

## Reported Findings

### RS-STATUS-001: Repeat Sentence

- Assigned evaluator: Bindu.
- Source: User's report on 23 October 2026.
- Report: "repeat sentence is all good and working."
- Classification: Reported pass; detailed evidence not supplied for this review.
- Action: No fix proposed. Preserve working behaviour in future regression tests.

### RA-001: Omitted Words Reappear in Transcript; Fillers and Pauses Receive High Marks

- Task: Read Aloud (`read_aloud`).
- Assigned evaluator: Santhi, according to the user's assignment list. The
  document itself does not identify its author.
- Date received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/PTE.docx`, table row 2.
- Evidence type: Trainer's written scenario and observation, not original output.
- Question ID/name, response/session IDs, evaluation date, model and policy
  version: not supplied.
- Full exam or single-question practice: not supplied.

#### Trainer Report

Candidate behaviour:
> I skipped words from the source during the reading and used fillers and pauses.

Observed system behaviour, as reported:
> The transcript still showed the words I skipped, and high marks were awarded for content and fluency

Trainer's expected behaviour, verbatim:
> Transcript will highlight missed and mispronounced words and marks will be deducted accordingly. Marks will be deducted for content (words were skipped )and for fluency( fillers and pauses).

#### Our Assessment

- Classification: Reported issue; insufficient evidence to confirm the cause.
- If the recording confirms omissions that are absent from the stored transcript,
  downstream text alignment can mistakenly treat those words as spoken. That
  could explain inflated Content, but does not establish why the words appeared.
- Potential causes to distinguish: ASR reconstruction, use of the wrong recording
  or transcript, answer/reference substitution, cache/input identity, or display
  of a reference passage in place of the candidate transcript.
- Fillers and pauses may be omitted from text transcription. Fluency needs the
  actual recording/timing evidence; a polished transcript is not sufficient.
- Word omission belongs in reference-versus-spoken-content analysis. A word
  absent from the candidate transcript cannot simply be highlighted inside that
  transcript; missing-word display needs an explicit reference alignment.
- Pronunciation feedback must be supported by audio evidence. A transcript alone
  cannot establish which sounds were mispronounced.
- Confidence: High that the report raises a testable discrepancy; no confidence
  assigned to a particular technical cause without the original evidence.

#### Evidence Still Needed

- One exact source passage/question and its matching candidate recording.
- The stored transcript and actual evaluation output, with scores/maxima.
- Santhi's identification of omitted words and noticeable fillers/pauses.
- Response ID, or session ID plus question name, if available.

#### Deferred Fix and Acceptance Case

- No fix selected or implemented.
- After verification, any correction must prevent unspoken reconstructed words
  from being accepted as proven spoken content and preserve valid readings.
- Acceptance comparison: the same passage read correctly versus with deliberate
  omissions and disruptions; compare recorded evidence, transcript, alignment,
  Content and Fluency separately. Do not prescribe numerical deductions yet.

### RA-002: Extremely Fast or Unclear Reading Receives a Perfect Transcript and High Marks

- Task: Read Aloud (`read_aloud`).
- Assigned evaluator: Santhi by the assignment list; author not named in the file.
- Date received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/PTE.docx`, table row 3.
- Evidence type: Trainer's written scenario and observation, not original output.
- Question, response/session IDs, evaluation date, model/policy version, exam
  mode and numerical scores: not supplied.

#### Trainer Report

Candidate behaviour:
> I also attempted at an extremely fast pace, where words are mispronounced or reduced to a mere buzzing sound.

Observed system behaviour, as reported:
> system still generates a flawless transcript matching the question perfectly. High marks are awarded for content, pronunciation and fluency.

Trainer's expected behaviour, verbatim:
> Transcript will highlight words missed, words mispronounced etc..and marks will be deducted (pronunciation and content)

#### Our Assessment

- Classification: Reported issue; original audio and evaluation needed.
- This is related to RA-001 but tests rushed/unclear delivery rather than explicit
  omissions and hesitation. Keep it as a separate scenario.
- A correct-looking transcript does not prove clear articulation. Recognition can
  infer likely words; the report does not yet establish whether this happened,
  or whether the shown text came from another source.
- Fast delivery alone must be distinguished from genuinely unintelligible or
  missing speech. Do not select an automatic pronunciation/content deduction
  based solely on words per minute.
- Separate checks are needed for actual audibility, recognized content, measured
  delivery timing and the evidence used for pronunciation scoring.
- Compare the evaluation date/version with deployed speech safeguards. Do not
  assume this result was produced by the newest code or model.
- Confidence: The concern is specific enough to investigate; the alleged perfect
  transcript and inflated scores remain unverified without actual outputs.

#### Evidence Still Needed

- Original fast/unclear recording and the exact passage used.
- Stored transcript, criterion scores/maxima, feedback and guardrail evidence.
- Response ID or another identifier linking the audio to that evaluation.
- Trainer's notes on which stretches were unintelligible or mispronounced.

#### Deferred Fix and Acceptance Case

- No fix selected or implemented.
- Compare normal clear reading, fast but clear reading, and fast unclear reading
  of the same passage. Evaluate content, fluency and pronunciation independently.
- Preserve good fast-but-clear responses; do not use transcript correctness as
  proof of pronunciation quality or award content for words not supported by audio.

## Describe Image Report from Athira

- Task: Describe Image (`describe_image`). Assigned evaluator: Athira, according
  to the user's assignment and supplied filename.
- Date received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/DI - Athira.docx`.
- Evidence: Five labelled attempts containing ten embedded screenshots, all
  visually inspected. Each pair shows the result, rubric criteria and transcript.
- Apparent workflow: Single-question evaluation, based on the displayed question
  score and transcript view. Server confirmation is still needed.
- The transcripts all discuss a plastic-recycling process and show a question
  maximum of 5.6 Speaking marks. The original image is NOT included; do not assume
  that every described stage or their ordering is correct merely from the text.
- Missing across all five: Question/paper name, question ID, response/session
  identifiers, original audio, evaluation timestamps, model/version, raw scoring
  evidence and gate decisions.
- The headings express the document author's intended test categories. No
  separate expected numerical scores or written explanation of objections is
  supplied. Do not treat those headings as independently established proficiency.

### Visible Results

| Case | Document Heading | Content | Oral Fluency | Pronunciation | Rubric Total | Question Contribution |
| --- | --- | --- | --- | --- | --- | --- |
| DI-001 | First Attempt - High Score | 4/6 | 5/5 | 3/5 | 12/16 | 4.2/5.6 (75%) |
| DI-002 | Second Attempt - Moderate | 6/6 | 3/5 | 3/5 | 12/16 | 4.2/5.6 (75%) |
| DI-003 | Third Attempt - Low | 4/6 | 3/5 | 2/5 | 9/16 | 3.15/5.6 (56.25%) |
| DI-004 | Fourth Attempt - Template | 5/6 | 4/5 | 3/5 | 12/16 | 4.2/5.6 (75%) |
| DI-005 | Fifth Attempt - Grammatical errors | 5/6 | 5/5 | 3/5 | 13/16 | 4.55/5.6 (81.25%) |

All five displayed conversions match `(rubric total / 16) * 5.6`. There is no
visible arithmetic discrepancy in these screenshots. That does NOT establish
that the underlying rubric marks are accurate.

### DI-001: First Attempt - High Score

- Embedded evidence: `word/media/image2.png` and `word/media/image10.png`.
- Feedback shown: "Overall accurate description of the recycling process, but
  the term 'excretion' should be 'extrusion'; otherwise the depiction is coherent."

Displayed transcript:
> The image illustrates the process of plastic recycling from waste collections to the production of reusable plastic granules. Overall, the process involves several stages including sorting, shredding, washing, melting, excretion, pelletizing. Initially, plastic waste is collected in different recycling bins and transported in a large container. Next, the collected plastic is shredded into small pieces. These pieces are then washed to remove dirt and other impurities from being moved along a conveyor belt. In the following stage, the cleaned plastic is melted and passed through an extrusion machine. Finally, the processed material undergoes pelletizing to produce small plastic granules which can be used to manufacture new plastic products.

Assessment:

- Confirmed visible observation: The transcript contains both "excretion" and
  "extrusion"; the feedback explicitly identifies the terminology issue.
- It is not yet known whether "excretion" was actually spoken or introduced by
  transcription. The original recording is needed to separate those causes.
- Whether Content 4/6 and Fluency 5/5 are appropriate cannot be established
  without the actual diagram, rubric bands and recording/timing evidence.
- Classification: Result/transcript documented; grading accuracy unverified.
- Deferred acceptance comparison: Accurate terminology versus deliberately
  substituted terminology, evaluated against the same image and original audio.

### DI-002: Second Attempt - Moderate

- Embedded evidence: `word/media/image5.png` and `word/media/image9.png`.
- Feedback shown: "The description accurately covers the main steps of plastic
  recycling in logical order; pronunciation and fluency are adequate with minor limitations."

Displayed transcript:
> The image shows a process of plastic recycling. First plastic waste is collected in different coloured bins, then the waste is taken to a machine where it is shredded into small pieces. After that the plastic pieces are washed with water and carried on a conveyor belt. Then the plastic is melted and processed through an extrusion machine, finally the material is converted into small granules. These granules can be used to make new plastic products. Overall plastic recycling involves several steps to reuse waste materials.

Assessment:

- The 75% tie with DI-001 is explained by different criterion combinations:
  `6 + 3 + 3 = 12` versus `4 + 5 + 3 = 12`. A tied total alone is not a bug.
- Full Content is possible alongside lower Fluency/Pronunciation; the heading
  "Moderate" does not itself establish that Content should be lower.
- Verify actual image coverage, stage relationships and audio before judging
  the 6/6 Content or the two 3/5 speech scores.
- Classification: Arithmetic consistent; criterion calibration needs evidence.

### DI-003: Third Attempt - Low

- Embedded evidence: `word/media/image4.png` and `word/media/image3.png`.
- Feedback shown: "You described the main recycling process clearly, but some
  key stages and details from the image were missing."

Displayed transcript:
> The image is about plastic recycling. There are many bins with different colors. People put plastic waste in the bins, the plastic goes into a machine and becomes small pieces. Then it is washed and melted. After that, the machine makes small plastic granules. Recycling is very useful for the environment.

Assessment:

- The screenshot shows a lower total than DI-001/002, with lower Pronunciation
  and less detailed text. This establishes a visible score difference, not its
  correctness.
- The feedback does not identify which image stages were missing. After obtaining
  the image, check whether the explanation can name the actual omissions.
- Content 4/6 matching DI-001 may or may not be justified by the rubric; DI-001
  has more detail but also the noted term error. No expected replacement score
  should be assigned yet.
- Classification: Needs source/audio verification; possible feedback-specificity gap.

### DI-004: Fourth Attempt - Template

- Embedded evidence: `word/media/image1.png` and `word/media/image7.png`.
- Feedback shown: "The response accurately describes most main stages of the
  recycling process, with generally clear but slightly limited pronunciation
  and minor fluency disruption."

Displayed transcript:
> The given image illustrates a process of plastic recycling. First and foremost, it consists of several stages, starting with the collection of plastic waste and ending with the production of the reusable granules. Then, plastic waste is collected in different colored bins. Subsequently, the waste is shredded into smaller pieces and washed to remove impurities. Following this, the cleaned plastic is transported along a conveyor belt and melted. It is then processed through an extrusion machine and converted into small granules. In conclusion, the image clearly demonstrates how plastic waste can be processed.

Assessment:

- The label "Template" alone does not establish that this is an invalid answer.
  The displayed text includes connected recycling-specific stages, not solely
  interchangeable filler or isolated topic keywords.
- Phrases such as "First and foremost," "Subsequently," and "In conclusion"
  are not sufficient evidence for an automatic zero by themselves.
- The diagram is needed to establish whether those details actually match it.
  Raw integrity-check evidence and the version used are needed to assess whether
  any applicable template gate ran and whether its decision was justified.
- Do not classify the 75% result as a confirmed template-gate failure from the
  heading alone. Ask what Athira specifically intended this attempt to test.
- Classification: Requires clarification; potentially legitimate structured answer.
- Deferred acceptance comparison: A structure containing accurate source-specific
  information versus the same structure filled with unrelated/generic material.

### DI-005: Fifth Attempt - Grammatical errors

- Embedded evidence: `word/media/image8.png` and `word/media/image6.png`.
- Feedback shown (Arabic word preserved as a Unicode escape for this ASCII record):
  `The response covers most main recycling \u0645\u0631\u0627\u062d\u0644 accurately, but it misses some image details and contains several grammar errors; pronunciation is understandable and fluency is smooth.`
- The escaped word is the visible Arabic word for "stages." It appears in both
  feedback screenshots within otherwise English text.

Displayed transcript:
> The image show the process of plastic recycling. First peoples collects plastic waste in different coloured bins. Then the waste are taken to a machine for shredding into small pieces. After that the plastic pieces is washed with water and moved through a conveyor belt. Next the plastic is melt and passed through an extrusion machine. Finally, it is convert into small granules. This process helps to reduce plastic waste and protect the environment.

Assessment:

- Confirmed visible observations: Grammar errors appear in the displayed text;
  the feedback acknowledges them. The displayed total is the highest of these
  five attempts, driven by Content 5/6 and Fluency 5/5, not an arithmetic error.
- Describe Image uses Content, Pronunciation and Oral Fluency, not a separate
  Grammar criterion. Grammar errors alone do not establish that the whole answer
  should be zero or that an Essay-style grammar deduction is required. Verify
  their effect on conveyed meaning and the configured task rubric.
- Pearson's [Describe Image scoring description](https://www.pearsonpte.com/pte-academic/test-format/speaking-writing/)
  identifies those three criteria and assesses relevant image content and spoken
  delivery. This supports checking the correct task rubric rather than importing
  Writing criteria into this case.
- Fluency 5/5 cannot be validated from grammar mistakes or transcript text alone;
  inspect the actual delivery and timing evidence.
- The unexpected Arabic word is a confirmed visible feedback-language defect
  if the intended output is English, as this interface/report otherwise indicates.
  Its technical origin (provider output, stored data or rendering) is unconfirmed.
- Classification: Scoring concern needs rubric/audio verification; feedback
  language inconsistency is visible and recorded for later correction.

### Cross-Attempt Checks Deferred to Server Review

- Confirm the question/image and correlate all five response IDs with their recordings.
- Compare model, prompt, scoring, transcription and gate versions at evaluation time.
- Inspect why Pronunciation is exactly 3/5 in four of five attempts; this is an
  investigation lead, not proof of a fixed-score bug.
- Check whether the first transcript's disputed term came from the actual speech.
- Review Content calibration and make missing-detail feedback source-specific.
- Verify any template/repetition evidence rather than relying on attempt labels.
- Trace the unexpected Arabic feedback word without changing historical results.
- Keep score arithmetic unchanged unless actual stored evidence reveals a mismatch.

## Retell Lecture Report from Salini

- Assigned evaluator: Salini, per the assignment list and supplied filename.
- Received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/Re-tell lecture Evaluation-Salini (1).docx`.
- Evidence: Six attempt headings and twelve distinct embedded screenshots.
  `word/media/image4.png` is inserted twice in the document.
- These are displayed single-question evaluation results; exact response IDs,
  question ID/name, evaluation time, model and policy versions are not supplied.
- Original lecture audio/reference and candidate recordings are not supplied.
  The displayed transcripts/feedback suggest a sustainable farming/food-security
  lecture, but they are not a substitute for the actual source.
- The headings describe the trainer's intended scenarios. There is no separate
  written explanation of expected numerical marks in this report.

### Visible Results and Screenshot Association

| Case | Trainer's Heading | Content | Oral Fluency | Pronunciation | Listening | Speaking | Displayed Total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RL-001 | First attempt - High score | 6/6 | 5/5 | 2/5 | 6/6 | 3.85/5.5 | 9.85/11.5 (85.65%) |
| RL-002 | Second attempt - Moderate score | 5/6 in image3; 4/6 in image4 | 5/5 in image4 | 2/5 in image4 | 5/6 in image3; 4/6 in image4 | 3.85/5.5 in both | 8.85/11.5 (76.96%) in image3; details conflict |
| RL-003 | Third attempt - Less content | 2/6 | 2/5 | 1/5 | 2/6 | 1.65/5.5 | 3.65/11.5 (31.74%) |
| RL-004 | Fourth attempt - Template | 4/6 in repeated image4; 5/6 in image8 | 5/5 in both detail images | 2/5 in both detail images | 4/6 in image4; 5/6 in image8 | 3.85/5.5 in both | 7.85/11.5 (68.26%) in image7; image8 implies 8.85 |
| RL-005 | Fifth attempt - Off-topic | 0/6 after gate | 0/5 after gate | 0/5 after gate | 0/6 | 0/5.5 | 0/11.5 (0%) |
| RL-006 | Sixth attempt - low fluency and pronunciation | 3/6 | 2/5 | 2/5 | 3/6 | 2.2/5.5 | 5.2/11.5 (45.22%) |

Evidence mapping, using original DOCX media filenames:

- RL-001: image1 + image2.
- RL-002: image3 + image4 in document order; details do not match the summary.
- RL-003: image5 + image6.
- RL-004: image7 + reused image4 + image8 in document order.
- RL-005: image9 + image10.
- RL-006: image11 + image12.

The image4 details and feedback match image7's 7.85 total; image8's details and
feedback match image3's 8.85 total. This suggests mixed screenshot placement,
not proof of an application defect. Preserve the two transcripts as unassigned
between RL-002/RL-004 until the original response IDs resolve the association.

### RL-001: High Score

Displayed transcript, image2:

> The lecture discusses the critical challenge of feeding a growing global population and highlights sustainable farming as an essential solution. The speaker emphasizes that environmentally friendly methods such as reducing chemical usage, conserving water and promoting biodiversity are vital for long-term agricultural productivity and resilient ecosystems. Additionally, the lecture notes the importance of local production and distribution systems in minimizing carbon footprint, supporting local economies, and empowering communities. Finally, it concludes that transitioning to these path practices requires collaborative effort among governments, farmers, and consumers through education, technology, and support

Feedback: "Clear and accurate retelling that paraphrases the main ideas with
coherent structure."

- Visible arithmetic: Content 6/6 contributes 6 Listening marks; combined
  Fluency/Pronunciation 7/10 contributes 70% of 5.5 = 3.85 Speaking marks.
  Total 9.85 and 85.65% agree with those contributions.
- The high overall percentage is not evidence of a high Pronunciation mark:
  Pronunciation is only 2/5 here. Content and Fluency drive the total.
- Full Content and Fluency need verification against the lecture and recording.
  The unusual phrase "these path practices" may be spoken wording or ASR output;
  its cause cannot be inferred from the screenshot.
- Classification: Visible calculation consistent; grading unverified.

### RL-002 and RL-004: Moderate and Template Attempts with Mixed Evidence

RL-002's summary (image3) awards 8.85 and says:

> Content accurately captures main ideas with paraphrase, but includes a minor extrapolation and omits some details; pronunciation is limited while fluency is strong.

RL-004's summary (image7) awards 7.85 and says:

> The response captures the main lecture topic and some supporting points, but it is somewhat vague and contains several language errors; pronunciation is limited, while fluency is strong.

Transcript A, image4 (inserted under both headings; 4/6 Content):

> In the given lecture, the speaker was mainly talking about the topic food and farming problem for world. First and foremost, the speaker described how environment friendly methods like reduce the chemical and water can helping agricultural productivity. The lecturer then mentioned distribution systems, reduces carbon footprint by transportation of foods. In addition, he highlighted making sustainable farming and effort and collaboration of stakeholder. He supported the notion and illustrated it briefly with several examples. In conclusion, the speaker shed light on imperative information about food security and how we can better plan it future generation.

Transcript B, image8 (placed under Fourth attempt; 5/6 Content):

> The lecture is about sustainable farming and how it helps solve the problem of feeding the growing world population. Firstly, the speaker explains that eco-friendly methods like conserving water, reducing chemicals and protecting biodiversity help keep ecosystems healthy and productive. Second, focusing on local food systems can reduce carbon footprints from long-distance transport and support local communities. Third, however, making this transition needs collaboration between governments, farmers and consumers through new technologies and policies for global food security.

- Transcript A contains generic connective/filler wording, but also mentions
  farming, chemical/water use, productivity, distribution, transport emissions,
  stakeholders and food security. Transcript B also has topic-specific details.
- Neither the heading "Template" nor familiar openings alone proves an answer
  should be invalid. Compare substantive points against the actual lecture and
  inspect template-gate evidence before deciding whether a bypass occurred.
- A template label and repetition within one response are different claims;
  neither transcript visibly demonstrates extreme exact repetition on its own.
- Both detail screenshots show Fluency 5/5 and Pronunciation 2/5. Validate those
  traits against the actual recordings, not the written grammar or headings.
- Summary/detail totals are individually consistent for the likely pairings
  image3+image8 and image7+image4. The supplied document does not establish that
  either pairing was shown together by the application.
- Classification: Confirmed evidence-association ambiguity; template-gate and
  grading concerns require original source, recordings and stored results.

### RL-003: Less Content

Displayed transcript, image6:

> The given lecture provides a valuable information about sustainable farming practices. The speaker primarily discusses how ensuring access to sufficient and nutritious food is a critical challenge due to population growth furthermore, the speaker highlights that in environmentally friendly methods, reducing chemical overall importance.

Feedback describes an incomplete, unclear answer with limited detail and weak
delivery. The visible marks are Content 2/6, Fluency 2/5, Pronunciation 1/5.

- Calculation is consistent: Listening 2 + Speaking (3/10 x 5.5) = 3.65.
- The displayed result distinguishes this attempt from the high-content attempt;
  it is not evidence that every response receives high marks.
- The precise Content deduction and delivery ratings still require source/audio.
- Classification: Lower marks visibly awarded; grading calibration unverified.

### RL-005: Off Topic

Displayed transcript, image10:

> In the given lecture, the speaker was mainly talking about the history of modern space exploration and planetary colonization. First and foremost, the speaker described how rocket propulsion systems are used, liquid hydrogen and oxygen to escape earth's gravitational pull. Lecturer then mentioned the discovery of water ice on the solar polar caps of Mars and its importance for future human settlements. In addition, he highlighted that private aerospace companies are reducing the cost of satellite launches significantly. He supported the notion and illustrated it briefly with several examples. In conclusion, the speaker shed light on important information about space exploration.

Feedback calls this fluent but largely unrelated to the lecture. Image9 explicitly
states: "A scoring gate was applied because the following criterion received zero:
Content." Final contributions, displayed criteria and total are all zero.

- Confirmed visible behaviour: A Content-zero gate is applied in this example.
  This is not proof that the separate template gate ran or caused the zero.
- The off-topic classification is consistent with the document's farming-related
  attempts, but needs the actual lecture to verify independently.
- Confirmed display inconsistency: The contribution explanation retains "7 out
  of 10" delivery points and "Calculation: 70% of 5.5 = 0" while the criterion
  table shows zero delivery marks after the gate. The final zero is explained by
  the gate, not by ordinary multiplication. Record this as a gate-explanation
  clarity issue; the screenshot does not demonstrate a wrong final award.
- No scoring fix selected. Later acceptance should distinguish raw rubric marks,
  an applied override and effective marks without presenting a false equation.

### RL-006: Low Fluency and Pronunciation

Displayed transcript, image12:

> The speaker talking about population growth, you know, and sustainable farming practices. It uses like chemical reduction and water conservation and local production, reduces carbon footprint, so stakeholders must cooperate.

Feedback describes relevant points but an incomplete/unclear answer with uneven
delivery and limited pronunciation accuracy. Marks: Content 3/6, Fluency 2/5,
Pronunciation 2/5.

- Calculation is consistent: Listening 3 + Speaking (4/10 x 5.5) = 5.2 (45.22%).
- Fluency and Pronunciation are visibly reduced, matching the direction of the
  trainer's scenario. This does not independently validate how pauses, fillers
  or individual sounds were assessed.
- Classification: Reduced delivery marks observed; audio-based accuracy pending.

### Retell Lecture Follow-up After Collection

- Retrieve the lecture/reference and six response IDs, recordings, transcripts,
  raw evaluations, gate metadata, model and policy versions from production.
- Resolve RL-002/RL-004 screenshot ownership before comparing their marks.
- Compare relevant source points against Content marks, not just response length.
- Inspect evidence for the repeated 5/5 Fluency and 2/5 Pronunciation in the
  high/moderate/template screenshots. Similar marks alone are not proof of a
  fixed-score defect, and the screenshots are not all independent evidence.
- Preserve the working Content-zero gate and reduced marks on weak attempts.
- Review the gated-result explanation separately from scoring correctness.
- No retries, question edits or implementation during this intake.

## Summarize Group Discussion Report from Hitha

- Assigned evaluator: Hitha, per the assignment list and supplied filename.
- Received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/Hitha SGD Summary (1).docx`.
- Evidence: Eight written scenarios/opinions; attempts 3-8 have twelve distinct
  embedded screenshots. Attempts 1-2 explicitly have no screenshots.
- Original discussion audio/reference and candidate recordings are not supplied.
  Hitha identifies the discussion as compulsory physical education; the displayed
  transcripts in attempts 3-7 concern that topic. Attempt 8 concerns pets.
- The UI includes "Choose another question" and appears to be single-question
  practice. Question/response IDs, dates, model and policy versions are missing.
- Keep trainer recollections, visible values and independent assessment separate.
  No code, data or evaluation-state changes are authorized in this phase.

### Reported and Visible Results

| Case | Trainer's Scenario | Content | Oral Fluency | Pronunciation | Listening | Speaking | Total |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SGD-001 | Natural delivery, perfect content; no screenshot | Not supplied | Not supplied | Not supplied | Reported 9/9 | Reported 4.25/8.5 | Reported 14.95/17.5 (84%); figures conflict |
| SGD-002 | Template, frequent "and", broken sentences, key words; no screenshot | Reported 5/6 | Reported 4/5 | Reported 1/5 | Reported 7.5/9 | Reported 4.25/8.5 | Reported 11.75/17.5 (64%); actual ratio 67.14% |
| SGD-003 | Errors, poor grammar, many fillers | 4/6 | 2/5 | 2/5 | 6/9 | 3.4/8.5 | 9.4/17.5 (53.71%) |
| SGD-004 | Incomplete sentences, gaps, repeated words | 6/6 | 2/5 | 2/5 | 9/9 | 3.4/8.5 | 12.4/17.5 (70.86%) |
| SGD-005 | Indian accent, fast delivery, good content | 5/6 | 4/5 | 1/5 | 7.5/9 | 4.25/8.5 | 11.75/17.5 (67.14%) |
| SGD-006 | Attempted foreign accent, good speed/content | 6/6 | 5/5 | 3/5 | 9/9 | 6.8/8.5 | 15.8/17.5 (90.29%) |
| SGD-007 | Normal pace/content, cut off at time limit | 6/6 | 2/5 | 3/5 | 9/9 | 4.25/8.5 | 13.25/17.5 (75.71%) |
| SGD-008 | Deliberately unrelated pets story | 5/6 | 4/5 | 1/5 | 7.5/9 | 4.25/8.5 | 11.75/17.5 (67.14%) |

Screenshot mapping uses original `word/media/` filenames:

- SGD-003: image1 + image2. Image2 is anchored to the paragraph containing the
  next attempt's heading, but continues image1's criteria and matching feedback.
- SGD-004: image3 + image4.
- SGD-005: image5 + image6.
- SGD-006: image7 + image8.
- SGD-007: image9 + image10.
- SGD-008: image11 + image12.

All six screenshot-backed attempts have internally consistent displayed
arithmetic: Listening = Content / 6 x 9; Speaking = (Fluency + Pronunciation) /
10 x 8.5. This verifies the displayed calculation, not the underlying assessment
or whether this configured skill mapping matches the intended policy.

### SGD-001: Natural Delivery and Perfect Content

- Trainer description: "Natural, normal delivery with perfect content."
- Trainer opinion: "The score should have been slightly higher, but it is still reasonable."
- Written figures: 14.95/17.5 (84%); Listening 9/9; Speaking 4.25/8.5.
- Evidence limitation: No screenshot, transcript, recording or raw criteria.
- Confirmed document discrepancy: 9 + 4.25 = 13.25, not 14.95. Also, 14.95 /
  17.5 = 85.43%, not 84%. Do not attribute these inconsistencies to the system
  without the actual saved result.
- Classification: Trainer considers the result broadly reasonable; marks and
  arithmetic need reconciliation from production later.

### SGD-002: Template Wording and Repeated Connectors

- Trainer description: "Used templates, repeated the word 'and' frequently, and
  had broken sentences, but included the key words."
- Trainer opinion: "This seems reasonable, but the score should have been slightly lower."
- Reported criteria: Content 5/6, Fluency 4/5, Pronunciation 1/5. Contributions
  7.5 + 4.25 = 11.75 are consistent with those figures.
- Confirmed document discrepancy: 11.75/17.5 is 67.14%, not the reported 64%.
- No original text/audio or gate output is supplied. Repetition of a common
  connector alone does not prove template domination or artificial extension;
  inspect density, substantive source points and actual delivery later.
- Correct key words alone are not proof of an accurate discussion summary.
  Verify propositions, speaker positions and relationships rather than assuming
  word presence is sufficient.
- Classification: Reported mild over-award; no independently confirmed gate or
  grading defect from this text-only account.

### SGD-003: Grammar Errors and Fillers

- Trainer describes errors, poor grammar and many fillers; opinion: "The score
  is slightly high, but it is still understandable because I included some key words."
- Visible feedback: "Content captures main ideas but includes inaccuracies and
  uneven coherence; pronunciation and fluency are limited per analysis."
- Transcript begins: "Three students were discussing physical education courses.
  First student said physical education was embarrassing and a waste of time."
  It mentions coordination, a coach's correction, GPA, changing/showering/travel
  time, swimming, stress relief, concentration, asthma, grading and alternatives.
- Visible awkward wording includes "he wanted major courses instead of sports
  and running around the court" and "extra time and academic pressure and
  subjective grading."
  These are transcript observations, not proof of what was actually spoken.
- Fluency and Pronunciation are both 2/5, so delivery marks were reduced. The
  transcript still conveys multiple topic-specific positions; grammar errors
  do not by themselves establish zero Content.
- Classification: Arithmetic consistent, reduced delivery marks observed;
  Content calibration and omitted fillers need source/audio verification.

### SGD-004: Fragmented Response Receives Full Content

- Trainer description: "No complete sentences, frequent gaps, and repeated words."
- Trainer opinion: "This score is too high for this response. It should have
  been around 9/17.5, and getting 9/9 in Listening does not make sense."
- Visible result: Content 6/6; Fluency 2/5; Pronunciation 2/5; Listening 9,
  Speaking 3.4, total 12.4. Do not adopt the suggested 9/17.5 without a rubric
  comparison and the actual recording.
- Feedback: "The response accurately captures main ideas and key details from
  all participants and presents a coherent synthesis; however, pronunciation
  and fluency are limited by the provided performance."
- Transcript excerpts: "Three students were discussing about physical education
  courses. That was two male students and one female student." Later: "He also
  talked about zero coordination, coach correcting poster, everyone. Moreover,
  affecting his GPA was also talked. Taking time for major courses was also
  mentioned. Three hours of weekly for changing clothes, showering and traveling."
- The remainder mentions swimming/stress/concentration/sleep, asthma, unfair
  grading, pass/fail, yoga/walking clubs and hiking/dance without competition.
- Priority within this case: Check whether full Content is justified by correct
  meaning, speaker attribution and synthesis, or whether keywords are being
  over-credited. The description "coherent synthesis" needs reconciliation with
  the visible fragments; it is not sufficient evidence to confirm full marks.
- Full Listening here is mechanically derived from full Content, not an
  independent direct assessment of listening ability. Weak delivery is already
  reflected in the 2/5 traits; that alone does not prove Content must also fall.
- Classification: Substantive Content-calibration concern; source/audio needed
  before confirming an over-award or selecting new scoring rules.

### SGD-005 and SGD-006: Accent and Delivery Comparison

- SGD-005 description: "Indian accent, fast delivery, and good content."
  SGD-006: "Attempted a foreign accent, with good speed and good content."
  Hitha considers both results accurate.
- SGD-005 feedback: Main ideas and key details captured with coherent structure;
  pronunciation limitations constrain the maximum while fluency is reasonably
  smooth. Marks: Content 5, Fluency 4, Pronunciation 1.
- SGD-006 feedback: "Clear, accurate synthesis of all speakers' points with
  logical organization; strong fluency, but pronunciation remains a band 3."
  Marks: Content 6, Fluency 5, Pronunciation 3.
- Both visible transcripts cover physical education: the first student's
  humiliation, coordination/GPA and time concerns; the second's swimming,
  stress/concentration/sleep and body-awareness benefits; the third's asthma,
  fitness-test fairness and grading concerns; pass/fail and optional activities.
- SGD-005 ends: "Overall, the students agreed that physical education was
  valuable but needed to be more flexible and less stressful." SGD-006 ends
  with substantially the same conclusion, but the full transcripts are not
  identical, so this is not a controlled accent-only experiment.
- Visible score difference is 4.05: Listening +1.5 from Content 5 to 6, and
  Speaking +2.55 from combined delivery 5/10 to 8/10. Arithmetic is consistent.
- The labels do not establish that a foreign accent caused the higher mark or
  that an Indian accent caused a penalty. Later compare actual intelligibility,
  articulation, timing, transcripts and source coverage under the same rubric;
  neither accent label nor speed alone justifies selecting a mark.
- Classification: Trainer-reported acceptable results; useful calibration pair,
  not confirmed accent bias or pronunciation accuracy.

### SGD-007: Abrupt Ending at Time Limit

- Trainer description: "Normal pace and correct content, but an abrupt ending
  because I exceeded the time limit." Opinion: "This score seems accurate."
- Visible result: Content 6/6, Fluency 2/5, Pronunciation 3/5; total 13.25.
- Feedback describes main ideas and all speakers' positions with coherent
  organization, with pronunciation/fluency limitations reflected in the metrics.
- Transcript covers the same physical-education positions and compromises and
  ends: "This was a very informative discussion about."
- The trailing fragment is visible; the reason for the cutoff is trainer-reported,
  not independently established. Fluency is reduced, but the screenshot does
  not identify which part of that deduction came from the ending.
- Classification: Trainer-reported pass; preserve as a regression case after
  the source, recording duration and evaluation evidence are collected.

### SGD-008: Pets Story Awarded High Content for a Reportedly Unrelated Discussion

- Trainer description: "Completely irrelevant content. The actual discussion
  was about compulsory physical education, but I spoke an imaginary story
  about three students discussing their pets."
- Opinion: "The score is surprisingly high and does not make sense, considering
  that my response was completely unrelated to the given topic."
- Screenshot result is unambiguous: Content 5/6, Fluency 4/5, Pronunciation 1/5;
  Listening 7.5/9, Speaking 4.25/8.5, total 11.75/17.5 (67.14%). No gate is shown.
- Feedback: "Content captures the main ideas and most details of the discussion,
  but pronunciation is very limited (band 1) and fluency could be smoother."

Displayed transcript, image12:

> In this discussion, three students were basically talking about the pet animals they just keep in their house. The first student said they own an elephant and that elephant is black in color, it has some big ears and it is very talkative and it always communicates to the favorite food. The second student then talked about a pet animal of his which is a dog and that dog is a corgi and surprisingly the corgi was a vegetarian. The corgi doesn't speak, it barks and it behaves like a normal dog and he said it loves a lot of attention. And the corgi was also three years old. The third student then went on discussing about her pets. She actually said she kept a butterfly at her home and they actually built a garden for that particular butterfly. And she also said an amazing fact that the butterfly is 40 years old. Along with the butterfly, there is also a black color snake in their garden and that snake is very friendly even if it is poisonous. She also said that next to that particular garden, they have built a big river for some exotic animals and exotic fishes to live. So she actually keeps, so all the other students said, the third student is actually keeping a particular jungle in her home rather than keeping pet animals. Anyways all of them were laughing at the characters and features of the animals or the pet animals they keep in their home and they went back to home after seeing all these details.

- Highest-priority SGD finding: If the matching question/reference is the
  reported physical-education discussion, neither Content 5/6 nor this feedback
  is supported by the visible response. It requires source-grounding review,
  not a change to the arithmetic, which correctly applies the awarded criteria.
- Confirmed evidence: Pets transcript, positive relevance feedback and nonzero
  Content/award are visible together. Original source identity is still missing,
  so the grading defect remains strongly suspected rather than independently
  confirmed against the actual input used by the evaluator.
- Do not declare the cause to be only AI weakness, only a prompt bug, a missing
  gate, or bad question setup. Check source configuration, source passed to AI,
  candidate/reference separation, response identity/cache and raw assessment.
- The issue is irrelevance, not whether the imaginary story itself is plausible
  or whether it uses a generic three-speaker summary structure.
- Future acceptance case after source verification: The same physical-education
  source with a faithful summary versus the unrelated pets story. Apply the
  configured relevance/Content-zero policy and trace the effective skill awards.
  Do not require every unrelated response to match this exact example's wording.

#### SGD-008 Production Record Located

- Evidence: User-pasted output from a read-only production query during this
  review. No direct server connection or independent remote execution by Codex.
- Matching model/ID: `SingleResponse`, primary key `289`.
- Candidate: `Hitha - Abe Services`.
- Question: `680`, `BB-SGD 1`; paper: `Bindu-T2`.
- Submitted: `2026-10-15 09:37:34.009184+00:00`; status: `completed`.
- Saved awards: Speaking `4.25`, Listening `7.5`. Their sum `11.75` matches
  the supplied report. The transcript excerpt includes the same elephant/corgi
  story, identifying this as the strong match for SGD-008.
- Search scope: 17 SGD SingleResponses yielded one match. The other four hits
  were UserResponses to question `305`, `SGD 2 SALINI`, paper `Salini`, whose
  transcripts discuss keeping small pets. They are different source/task records
  and do not establish additional off-topic defects.
- What is now verified from supplied server output: identity, timestamp, saved
  status, award values and matching candidate excerpt. Still missing: actual
  question/source, historical source passed to evaluation, full result, model,
  prompt/context and gate evidence. Root cause is not yet established.
- Next step: Read question 680's current source and response 289's stored result,
  preserving both before any retry. Current question fields are not necessarily
  the historical fields used on 15 October; check retained evidence separately.

#### SGD-008 Saved Evaluation and Current Reference Inspected

- Evidence source: User attachment
  `/home/devaccolades/.codex/attachments/212324a3-59e7-44a6-9655-f5d1582c9750/Pasted text.txt`.
  It records the read-only production inspection of SingleResponse 289.
- Stored mode: `v2`. Saved model: `gpt-5-nano`. Prompt hash:
  `003718d2f9c54d2ab2eaf40300be8140102d4e7d5dfed003715b058bcd7f50e3`.
- Current question 680 has empty `text`, but a substantial `correct_answer`
  reference about mandatory PE: opposition over stress/time/unfairness, support
  for health/stress/concentration/sleep, and a compromise of inclusive choices
  such as yoga, walking, hiking and dance. Source audio is
  `questions/audio/SGD1_e9mvmbu.mpeg`. The audio itself has not been listened to.
- Empty question text alone does not establish a configuration defect: the
  current code uses the Correct answer field as examiner reference for SGD.
  Whether that reference existed and was included historically is unresolved.
- Stored answer payload is `{}`; candidate content appears in
  `transcribed_audio_data.transcription.text`, which contains the same full
  elephant/corgi/butterfly story as the report. An empty typed payload alone
  is not proof that the candidate answer was omitted from an audio evaluation.
- Saved criteria: Content `5/6`, Fluency `4/5`, Pronunciation `1/5`, total `10/16`.
  Feedback incorrectly describes good source coverage relative to the current
  PE reference. It matches the screenshot's feedback.
- Saved scoring evidence explicitly records Content-zero gate `applied=False`
  with no triggered traits. Correct arithmetic from those criteria produces
  Listening `(5/6)*9=7.5` and Speaking `(4+1)/10*8.5=4.25`.
- Therefore the immediate failure is not a proportional arithmetic error or
  proof that an already-triggered zero gate was ignored. The nonzero Content
  assessment allows the gate to remain inactive. Why Content became 5 is the
  next historical-context question.
- Repetition detector `repetitive-answer-v1` passes with ratio/score zero;
  known-template detector `known-answer-template-v1` passes with zero matches.
  These checks do not establish source relevance. The attached result shows
  no separate semantic-template assessment, prompt-copy check, `input_context`
  source hash or raw prompt. Absence from this saved wrapper does not prove
  no source material reached the provider or date every deployed component.
- Speech evidence is `speech-evidence-v2`: 263 words over 120.06 seconds,
  Fluency band 4 and Pronunciation proxy band 1. This confirms the stored
  delivery data/version, not the correctness of audio quality assessment.
- Current Content descriptors for bands 5/6 require accurate main ideas and
  speaker perspectives, so they do not support this pets response against the
  current PE source. Also record that the current band-0 wording only says
  "relevant to the prompt but too limited"; it does not explicitly describe
  an entirely unrelated summary. This is a rubric-review lead, not proof that
  wording caused this result, nor evidence of the historical rubric supplied.
- Classification: Confirmed saved high Content/awards inconsistent with the
  current reference and matching the trainer report. Historical input/source
  delivery, exact prompt and model reasoning remain unverified; a current-
  deployment regression has not yet been reproduced. Do not attribute the
  result to the newer configured model or silently rerun it.
- Next read-only check: Retained EvaluationJob/EvaluationAttempt and matching
  EvaluationCache records, their timestamps, versions and any source/prompt
  evidence. A prompt hash alone cannot recover the original prompt.

#### SGD-008 Historical Job and Cache Evidence

- Evidence: User-pasted read-only production history query during this review.
- One job: `EvaluationJob 1855`, engine `pte-evaluation-v2`, completed, created
  `2026-10-15 09:37:34.013456+00:00`.
- Job input keys: `answer_data`, `question_id`, `response_id`, `answer_audio`,
  `response_type`, `transcribed_audio_data`. No source/reference or rubric
  snapshot is exposed in that retained job input.
- Transcription attempt `2934`: `whisper-1`, started
  `2026-10-15 09:37:34.049360+00:00`. Prompt version empty; raw result empty;
  normalized result contains only `transcription`.
- Evaluation attempt `2935`: `gpt-5-nano`, started
  `2026-10-15 09:37:40.588150+00:00`. Prompt version empty; raw result empty;
  normalized keys `ok`, `model`, `evaluation`, `prompt_hash`, `integrity_checks`.
- Matching cache `2578`: `gpt-5-nano`, created
  `2026-10-15 09:37:53.198830+00:00`; result keys `scores`, `feedback`,
  `max_score`, `weighted_score`. It retains assessment, not original prompt or
  source. Its creation after the attempt began does not alone prove cache-hit
  status or expose the actual provider request.
- This narrows the historical evidence limit: the queried job, attempt and
  cache records do not recover which source/reference/rubric was supplied to
  the original evaluation. Empty raw-result fields are an auditability gap,
  not proof the provider received no reference or candidate answer.
- The old model and timestamps are verified from supplied server output. The
  exact historical code version/prompt is still unknown despite the engine
  label. Do not attribute this result to a later model or call it a reproduced
  current-deployment failure.
- Next non-mutating check: Reconstruct today's prompt for the saved candidate
  using current question/reference and deployed prompt builder, without calling
  evaluation, OpenAI or cache-writing helpers. Label it a current reconstruction,
  not the historical prompt. Check source/candidate inclusion and retain the
  current model and prompt-version identifiers before any approved live test.

#### SGD-008 Current Prompt Reconstruction Verified

- Evidence: User attachment
  `/home/devaccolades/.codex/attachments/ea69a5fa-cac4-4c94-9ccd-7a0fc3045435/Pasted text.txt`.
  The command reports read-only execution and `OPENAI_CALLED=false`.
- Current shell configuration: model `gpt-5.4-mini`; prompt version
  `pte-evaluation-prompt-v6`. This is not independently a check of the live
  Celery process's environment or a provider response.
- Reconstructed prompt hash:
  `80b86d1fb20adb0ea92f197493747941464e85992a26ec2a287c20a19baeb494`.
  It differs from the historical hash. That establishes different prompt input,
  not which historical source/rule/code changed.
- Recorded candidate hash:
  `1231a17905e304749da6db8f0e6a670a0963c8d094d2b9261fba620e5067be0b`.
  Recorded reference hash:
  `577a74bc8f17107778e544a6439cd286bffcda6016d01c9ab1ab92d3b6ca6717`.
- Full reconstructed text visibly separates `CANDIDATE_RESPONSE` (pets story)
  from `REFERENCE_MATERIAL` (mandatory PE discussion). Both inputs are present.
  Empty `QUESTION_TEXT` does not remove the PE reference from this prompt.
- Current instructions explicitly say an unrelated answer must receive zero
  Content, require lecture/discussion comparison with the reference and prohibit
  substituting an imagined answer. They also request `template_assessment`,
  source-connected specific points and a task-addressing judgment.
- Therefore missing reference/candidate text is not reproduced in this current
  reconstruction. It does not prove that the old request contained the source
  or that today's model will follow the instructions correctly.
- The reconstruction reuses stored `speech-evidence-v2` metadata. It does not
  retranscribe audio, verify current pronunciation/fluency measurement or test
  the complete live task/worker execution path.
- Next proposed step, requiring approval beyond read-only collection: One
  provider-only grading check with the reconstructed current prompt, retaining
  response 289 and cache records unchanged. This incurs an API charge and must
  not use task/orchestrator helpers that enqueue work or write results/cache.
  Inspect raw Content judgment before considering any historical repair.
- Expected Content for the supplied PE reference/pets response is zero. A zero
  from one controlled check would demonstrate that example's current model
  behaviour, not certify all source-relevance checks or all nine task types.
- No provider call, response retry, cache update or production repair performed.

### SGD Follow-up After Collection

- Prioritize SGD-008's question/response ID, actual discussion/reference, candidate
  recording/transcript, raw provider request/response if retained, context checks,
  gate metadata and model/policy version. Do not retry before preserving evidence.
- Reconcile SGD-001 totals and SGD-002 percentage from stored results; the written
  report's inconsistent numbers do not establish a calculation bug in the build.
- Compare SGD-003/004 against the source to distinguish meaningful coverage from
  keyword listing and to assess speaker relationships and coherence.
- Inspect SGD-002's actual response for repetition/template density and source
  specificity before proposing stricter gate thresholds.
- Keep grammar, fluency, pronunciation and source relevance distinct; do not
  infer audio quality from transcript grammar or accent labels.
- Use SGD-005/006 and SGD-007 as calibration/regression evidence, including the
  trainer's acceptable-result opinions, rather than recording only complaints.
- No implementation, reevaluation or stored-score changes during this intake.

## Respond to a Situation Report from John Sir

- Assigned evaluator: John Sir, per the assignment list and supplied filename.
- Received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/RTS John (1).docx`.
- Evidence: Nine cases, each with one distinct screenshot, plus written opinions.
  The first three also include written versions of the intended answer.
- Screenshot mapping: RTS-001 to RTS-009 correspond in order to
  `word/media/image1.png` through `word/media/image9.png`.
- The actual situation prompt, question/response IDs, candidate recordings,
  evaluation dates, model and policy versions are not supplied. The examples
  concern explaining a computer failure and missing an online class to a professor.
- The screenshots show question-level results and transcripts. Confirm the exact
  practice/session context from production later rather than assuming it.

### Visible Results

| Case | Scenario | Content | Oral Fluency | Pronunciation | Speaking Contribution | Displayed Percentage | Trainer Opinion |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RTS-001 | Extremely short, informal answer | 2/6 | 2/5 | 1/5 | 1.13/3.6 | 31.25% | Content should be below 1 |
| RTS-002 | Brief explanation and request for attendance | 5/6 | 5/5 | 2/5 | 2.7/3.6 | 75% | Content should be 2 or 3, not 5 |
| RTS-003 | Detailed, polite response | 5/6 | 5/5 | 3/5 | 2.92/3.6 | 81.25% | Evaluation seems fine |
| RTS-004 | Low fluency | 4/6 | 2/5 | 2/5 | 1.8/3.6 | 50% | Fluency should be below 1 |
| RTS-005 | Medium fluency | 5/6 | 2/5 | 3/5 | 2.25/3.6 | 62.5% | Scoring seems fine |
| RTS-006 | High fluency | 5/6 | 5/5 | 3/5 | 2.92/3.6 | 81.25% | Scoring seems fine |
| RTS-007 | Bad pronunciation | 4/6 | 2/5 | 1/5 | 1.57/3.6 | 43.75% | Scoring is fine |
| RTS-008 | Template | 0/6 effective | 0/5 effective | 0/5 effective | 0/3.6 | 0% | Scoring is fine |
| RTS-009 | Stem repetition | 0/6 effective | 0/5 effective | 0/5 effective | 0/3.6 | 0% | Scoring seems fine |

For non-gated examples, the displayed percentage equals the combined rubric
points divided by 16; the question contribution is that fraction of 3.6.
The screenshots show two-decimal contributions while percentages describe the
underlying rubric fraction. Values such as 13/16 x 3.6 = 2.925 appear as 2.92;
7/16 x 3.6 = 1.575 appears as 1.57. Record the displayed values as supplied;
rounding/formatting is separate from whether criterion marks are justified.
There is no material score-calculation mismatch established by these screenshots.

### RTS-001: Very Brief and Informal Response

Written answer supplied by trainer:

> Hey prof, pc dead. No class today.

Displayed transcript:

> Hey professor, PC dead, no class today.

- Visible feedback: "The message is too brief and overly informal; it should
  be more polite, apologize, and request class materials."
- Trainer opinion: "Response was too short and should have been awarded less
  than 1 for content."
- The output recognizes brevity and register problems and awards Content 2/6,
  not a high Content mark. Whether even 2 is excessive requires the exact
  communicative task and its configured descriptors.
- Do not impose a new minimum length or fractional mark solely to match the
  opinion. A short answer may communicate part of the task; required actions,
  clarity, appropriateness and the permitted rubric scale must be checked.
- The written "prof" versus displayed "professor" is a visible difference,
  but the intended written answer is not an independent recording. It does not
  establish that ASR invented speech.
- Classification: Disputed low Content award, not a confirmed grading defect.

### RTS-002: Brief Response Receives Content 5/6

Written answer supplied by trainer:

> Hello sir, my computer is not working so I cannot join online class today. Sorry for this. Please give me attendance.

The displayed transcript contains the same substantive wording, with different
sentence punctuation. Feedback states:

> Content is mostly appropriate and clear, but the message could be more formal and include a request for materials or a plan to catch up.

- Trainer opinion: "Eventhough better than the previous one the content is not
  exhaustive enough to be awarded 5. A score of 2 or 3 would be appropriate."
- Visible concern: Content remains 5/6 despite feedback identifying absent
  follow-up actions and formality limitations. The intended "attendance"
  request also needs comparison with what the situation actually asks for.
- This is the stronger Content-calibration lead in this report. Retrieve the
  original prompt and descriptors to distinguish optional improvements from
  missing mandatory task actions before choosing a different mark.
- RTS-002 and the much fuller RTS-003 both receive Content 5/6. This is a useful
  comparison, not automatic proof of a defect: a banded rubric can legitimately
  give different answers the same band when task requirements are met.
- Fluency 5/5 cannot be independently assessed from a concise written transcript.
- Classification: Suspected Content over-award; prompt/rubric/audio review pending.

### RTS-003: Detailed Polite Response Accepted by Trainer

Written answer supplied by trainer:

> Dear Professor Smith, I want to sincerely apologize for my inability to join today's online lecture due to a sudden hardware failure on my computer. I am currently working to resolve the issue as quickly as possible. In the meantime, I will review the assigned readings and catch up on the recorded lecture once available. Please let me know if there are any specific materials or announcements I should focus on. Thank you very much for your time and understanding.

- Visible result: Content 5/6, Fluency 5/5, Pronunciation 3/5; 81.25%.
- Feedback: "The response is clear and appropriate with only minor omissions,
  and the delivery is fluent though pronunciation shows some minor limitations."
- Trainer opinion: "The evaluation seems to be fine in this case".
- The written response includes explanation, apology, a repair/catch-up plan,
  a materials request and an appropriate closing. Which omissions justify
  Content 5 rather than 6 is unspecified in the feedback; check the actual
  prompt later rather than inventing missing requirements.
- Classification: Trainer-reported acceptable result; retain as a positive
  regression comparison for RTS-001/002, not independently verified audio scoring.

### RTS-004: Low Fluency Still Receives 2/5

Displayed transcript:

> Dear Professor Smith, I want to inform that I'll be unable to attend today's class. My computer has a problem. Thank you.

- Feedback: "The response is polite and relevant but brief, with limited detail;
  pronunciation and fluency are both below average."
- Trainer opinion: "Fluency score in this question should have been below 1".
- Visible result: Fluency is reduced to 2/5, with Content 4/6 and Pronunciation
  2/5. The claim concerns severity/calibration, not failure to deduct at all.
- The transcript cannot establish pause length, hesitation frequency, restarts
  or intelligibility. Obtain the original recording and timing evidence before
  deciding whether 0, 1 or 2 matches the permitted descriptors.
- Classification: Trainer-reported Fluency over-award; audio evidence required.

### RTS-005 and RTS-006: Medium and High Fluency Accepted by Trainer

RTS-005 displayed transcript:

> Dear Professor Smith, I want to inform you that I will be unable to attend today's online class due to unexpected technical issue with my computer. Thank you for your understanding. I will review the lecture slides and complete the reading assignments as soon as possible.

- Visible marks: Content 5/6, Fluency 2/5, Pronunciation 3/5; total 2.25/3.6.
- Feedback describes an appropriate, clear but somewhat brief answer and
  moderate fluency limitations. Trainer: "The scoring seems to be fine".

RTS-006 displayed transcript:

> Dear Professor Smith, I want to inform you that I will be unable to attend today's online class due to an unexpected technical issue with my computer. I apologize for the short notice. I will review the lecture slides and complete the reading assignments as soon as my device is repaired. Thank you for your understanding.

- Visible marks: Content 5/6, Fluency 5/5, Pronunciation 3/5; total 2.92/3.6.
- Feedback praises clarity and fluency but suggests asking for class materials
  or a recording. Trainer: "The scoring seems to be fine".
- Medium and High labels are trainer descriptions, not numeric rubric bands.
  Fluency 2/5 is accepted on RTS-005 yet disputed as too high on RTS-004; the
  recordings are needed to test whether the system adequately separates them.
- Classification: Two trainer-reported acceptable cases for future delivery
  calibration; no independent audio assessment made during intake.

### RTS-007: Poor Pronunciation Receives Reduced Marks

Displayed transcript:

> Dear Prof. Ashmeet, I want to inform you that you will be unable to attend today's online class due to an unexpected technical issue with my computer. I apologize for the short notice. I will review the lecture slides and complete the assigned assignments.

- Visible marks: Content 4/6, Fluency 2/5, Pronunciation 1/5; total 1.57/3.6.
- Feedback: "The response is relevant and polite but misses key details such as
  asking for materials or recording, and the delivery was uneven with low
  pronunciation clarity."
- Trainer opinion: "Scoring is fine".
- Reduced Pronunciation is visible. The transcript's "you will be unable" versus
  explaining the candidate's own absence is also worth checking against audio
  and source, not automatically attributing it to candidate wording or ASR.
- Classification: Trainer-reported acceptable poor-pronunciation result;
  preserve as a negative delivery example for later regression checks.

### RTS-008: Generic Template Receives Zero

Transcript excerpts:

> Good day to you, Professor. How are you doing today? I guess this is a good time to talk to you and hope you don't mind. I wanted to discuss with you online class.

> We need to also think about broken PC when we do this. I'm open to all your suggestions, which I'm sure you may have regarding this topic.

- Feedback: "The response is understandable and fluent, but it does not clearly
  explain that the computer is broken or ask to miss the class and receive
  materials."
- Visible banner: "A scoring gate was applied because the following criterion
  received zero: Content." Effective criteria, contribution and total are zero.
- Trainer opinion: "Scoring is fine".
- Confirmed visible behaviour: This example is rejected via the Content-zero
  gate. Topic words alone do not yield a nonzero award here.
- The screenshot does not identify a separate known-template, semantic-template
  or repetition detector. Do not claim that a dedicated detector caused the zero.
- Feedback refers to fluent delivery while the effective trait table shows zeros;
  raw delivery assessment and effective gated marks must be distinguished when
  examining stored output later. No wrong final award is established.
- Classification: Trainer-accepted rejection; keep as a gate regression example.

### RTS-009: Repeated Situation Stem Receives Zero

Displayed transcript:

> my computer is broken and I can't attend the online class how should i tell my professor My computer is broken and I can't attend the online class. How should I tell my professor? My computer is broken and I can't attend the online class how should tell my professor

- Feedback: "The response is relevant but too limited and repetitive for content,
  with very weak pronunciation but smooth overall fluency."
- The Content-zero banner is visible. Effective criteria, contribution and
  total are zero; trainer opinion: "Scoring seems to be fine".
- The text repeatedly describes the situation and asks how to tell the professor
  instead of actually making the requested communication. Original prompt is
  needed to confirm exact stem copying; the repetition is visible independently.
- This demonstrates a zero award on this example, not evidence that every prompt
  copy or repeated answer is caught or which specific detector ran.
- Classification: Trainer-accepted rejection; preserve both the repeated wording
  and task-fulfilment distinction for future tests.

### RTS Follow-up After Collection

- Retrieve the exact situation prompt, configured rubric and all nine response
  IDs, dates, recordings, stored transcripts, raw marks and gate metadata.
- Prioritize RTS-002 Content 5/6 against required communicative actions; compare
  RTS-001/003 without using length or politeness as a substitute for the rubric.
- Compare the actual low/medium/high-fluency recordings (RTS-004/005/006), then
  inspect timing evidence and descriptors before selecting deductions.
- Check whether Content feedback names optional improvements or required
  omissions. Vague references to "minor omissions" should not become assumed
  facts about a prompt not supplied with this report.
- Preserve acceptable cases RTS-003/005/006/007 and working zero results
  RTS-008/009. Distinguish Content-zero gating from dedicated template detection.
- Do not infer current-deployment behaviour from undated historical screenshots.
- No retries, code/configuration edits or stored-result changes during collection.

## SWT and Essay Report from Remarks PDF

- Assigned evaluator: Anupama for both tasks, according to the user's assignment
  list. The generic PDF title does not itself identify the tester. PDF Author
  metadata names "Godvin- Abe Services", which does not establish who tested it.
- Received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/Remarks.pdf`, all five pages reviewed
  visually and through extracted text. Page 1 is SWT; pages 2-5 cover Essay.
- Evidence: Four complete SWT answer texts and five complete Essay answer texts,
  with written remarks reporting scores. These are not original result
  screenshots or saved criterion/gate output.
- Missing: SWT source passage, exact Essay prompt, question/response IDs, actual
  submitted text as stored, evaluation dates, raw criteria, effective awards,
  scoring/model versions and policy settings at evaluation time.
- User's accompanying concern: Reversed meaning still earns SWT/Essay marks,
  and essays below 200 or around 150 words still earn above 20 with little
  score variation. Keep these as distinct checks, not one assumed root cause.

### Word Counts and Chronology

- Counts below apply the repository's current convention to the PDF answer text:
  Unicode NFKC normalization, whitespace splitting and counting tokens containing
  a letter/digit; hyphenated words and contractions without spaces count as one.
  Exclude headings, remarks and PDF page breaks. These are locally verified
  document-text counts, not confirmed production-submission counts.
- Current local [company strict Form policy](STRICT_FORM_POLICY.md) requires
  SWT 5-75 words in one complete sentence and Essay 200-300 words, inclusively.
  Ineligible Form means zero for the whole answer, not just the Form criterion.
- The local policy document is dated 20 October 2026. PDF CreationDate and
  ModDate are 15 October 2026. That metadata predates the documented policy
  update, but does not prove actual evaluation dates, deployment dates or that
  the PDF metadata is authoritative. Do not label these current-policy bypasses
  until the saved results and server rollout timeline are checked.
- Historical scores are not automatically rewritten by deploying a new policy.
  No retry or repair is authorized by this evidence-collection task.

### SWT Reported Results

| Case | PDF Label | Local Word Count | Reported Award | Assessment Focus |
| --- | --- | --- | --- | --- |
| SWT-001 | Wrong answer 1; capital letter after semicolon | 66 | Zero overall | Actual zero reason unknown; cannot attribute it to capitalization alone |
| SWT-002 | Wrong answer 2; negative content, 76 words | 76 | Zero overall | Outside current word limit; does not isolate semantic checking |
| SWT-003 | Wrong answer 3; negative content | 73 | 15/22.5; Reading 2.5/10, Writing 12.5/12.5 | Meaning reversal still earns reported marks; priority source-grounding check |
| SWT-004 | Wrong answer 4; TEMPLATE | 75 | 20/22.5 | Familiar syntax versus template domination; source fidelity/Form pending |

### SWT-001: Capitalization after Semicolons and Reported Zero

Answer begins:

> Climate change is affects disproportionately by indigenous communities around the world; They lived in harmony with nature, however, rapid climate change disrupted the delicate balance; Altered rainfall patterns and more frequent extreme weather events caused food shortages and water scarcity resulting in eroding their cultural heritage; They are actively participating in climate-related events, raising awareness; acknowledging their resilience is an opportunity to learn from their wisdom.

- Trainer remark: "gave capital letter after semicolon (got zero overall)."
- Local count is 66, within the current SWT word range. The text also contains
  grammar problems such as "is affects disproportionately by", independently
  of capitalization. Semicolon clauses are not automatically separate sentences.
- Without raw Form assessment, sentence-check output, Content assessment and
  override metadata, capitalization is only the trainer's interpretation of
  the zero, not a confirmed gate trigger or a justified new hard-zero rule.
- Classification: Reported zero, cause unverified; investigate possible false
  rejection separately from the nonzero meaning-reversal concern.

### SWT-002 and SWT-003: Meaning Reversal with and without Word-Limit Failure

SWT-003's full answer, page 1:

> Climate change has little impact on indigenous communities because rising temperatures and extreme weather conditions do not affect their food supplies, water resources, or traditional homes; indigenous people can easily preserve their cultural heritage without changing their lifestyles, and younger generations face no risk of losing traditional knowledge; therefore, their participation in climate change initiatives is unnecessary, and the global community does not need to consider their experiences when developing environmental protection strategies.

- SWT-003 is 73 words and reportedly earns 15/22.5, split as Reading 2.5/10 and
  Writing 12.5/12.5. The reported contributions add correctly, but no underlying
  criterion scores are supplied, so the mapping and Content gate cannot be
  independently reconstructed from the total.
- SWT-002 has the same wording except its ending is "environmental protection
  strategies or sustainable solutions." Those three added words make 76; its
  reported zero is compatible with a word-limit gate.
- This is a useful paired test: SWT-002's zero does not prove the evaluator
  detected reversal; it may have rejected only length. SWT-003 removes that
  length failure and leaves the semantic concern exposed.
- Statements deny effects on food/water/homes, cultural loss and the need for
  indigenous participation. The trainer/user identify them as the opposite of
  the source. Verify the actual source and evaluator context before confirming
  the grading defect or treating the expected meaning as independently known.
- If that reversal is confirmed, common topic words must not substitute for
  faithful propositions, relationships or conclusions. Review why partial
  Reading and full Writing credit survive, then apply the configured Content
  and gating policy rather than simply forcing a new preferred total.
- Classification: High-priority suspected source-fidelity/Content-gate issue;
  exact question context and original evaluation still required.

### SWT-004: Source-Specific Summary Labelled Template

Answer, page 1:

> Climate change is affecting indigenous communities, who traditionally lived in harmony with nature; however, rising temperatures and extreme weather events cause food shortages and damage to traditional dwellings, threatening their cultural heritage as younger generations adapt to environmental changes, indigenous people participate in climate-related initiatives, raise awareness, and advocate sustainable solutions, highlighting their resilience and emphasizing the importance of involving them in climate mitigation and adaptation efforts to learn from their traditional knowledge and wisdom.

- Reported score: 20/22.5; local count: exactly 75, so not over the current limit.
- The PDF bolds wording such as "who", "threatening", "highlighting" and
  "and emphasizing the importance of". Highlighted linking structures or common
  relative/participial constructions do not alone establish template domination.
- This answer includes topic-specific effects, cultural risks, participation and
  proposed solutions. Compare them against the source rather than automatically
  zeroing any answer that uses familiar sentence structures.
- The long sequence around "environmental changes, indigenous people
  participate" needs grammar/Form review; do not infer full sentence compliance
  merely from one final full stop or invent a gate reason without saved output.
- Classification: Reported template concern; no proven template-gate bypass.

### Essay Reported Results

Use unique review IDs because the PDF labels both its short third answer and
its final wrong-content answer as "Wrong answer 3".

| Case | PDF Label | Local Word Count | Reported Writing Award | Current Word-Count Eligibility |
| --- | --- | --- | --- | --- |
| WE-001 | Correct answer | 293 | 25.85/28 | Within 200-300 |
| WE-002 | Wrong answer 1: TEMPLATE | 275 | 23.69/28 | Within 200-300 |
| WE-003 | Wrong answer 2: UNDER 200 WORDS; reported approximately 175 | 187 | 23.69/28 | Outside; current company policy requires whole-answer zero |
| WE-004 | Wrong answer 3: UNDER 150 WORDS; reported approximately 135 | 143 | 22.62/28 | Outside; current company policy requires whole-answer zero |
| WE-005 | Wrong Answer 3: ENTIRELY WRONG CONTENT | 276 | 19.38/28 | Within 200-300; argument quality is a separate check |

### WE-001: Baseline Essay Labelled Correct

- Pages 2; 293 words, reported 25.85/28.
- Position: Modern life harms mental health through work/financial pressure and
  social-media comparison. Examples include overtime/burnout and unrealistic
  online expectations. Conclusion recommends balance and realistic expectations.
- First sentence: "The modern lifestyle is becoming increasingly fast-paced,
  leaving people with less time to maintain their mental health."
- A plausible positive comparison for the task, not a confirmed full-credit
  answer without the actual question and raw rubric output. The report's label
  "Correct answer" is not an authoritative answer key for opinion writing.
- Classification: Reported positive baseline; retain for comparative analysis.

### WE-002: Topic-Relevant Essay Labelled Template

- Pages 2-3; 275 words, reported 23.69/28.
- Generic opening includes "In today's modern world", "has become increasingly
  important" and "This essay will discuss the major reasons behind this issue".
- The body nevertheless discusses work deadlines, burnout, sleep, social-media
  comparison, screen time and weakened face-to-face relationships, with examples
  connected to the stated mental-health topic.
- Bolded connective/framework language in the PDF does not prove an answer is
  devoid of meaningful task-specific reasoning. Evaluate template coverage,
  substantive argument and the actual prompt, not the mere presence of an
  introduction/body/conclusion framework.
- Same reported 23.69 as WE-003 is a review lead, not proof of copied output,
  caching or identical raw criterion marks. A quantized rubric can yield ties.
- Classification: Reported template concern; requires original evaluation and
  detector evidence before deciding whether a gate should have applied.

### WE-003 and WE-004: Under-Length Essays Still Reported above 22/28

WE-003, page 3, full supplied answer:

> In today's modern world, the issue of whether modern life is too fast-paced for good mental health has become increasingly important. I strongly agree because it negatively affects people's mental well-being and quality of life.
>
> One of the main reasons is the growing pressure to achieve professional and financial success. Many people struggle to manage work and personal responsibilities, leading to stress, anxiety, and exhaustion. For example, employees who work long hours may experience burnout and find it difficult to maintain a healthy work-life balance. Therefore, a fast-paced lifestyle can harm mental health.
>
> Another significant factor is the influence of social media and modern technology. People often compare themselves with others, which can lead to insecurity and dissatisfaction. For instance, young adults who compare their lives with others online may feel stressed and unhappy. Furthermore, excessive screen time can reduce meaningful communication and relaxation.
>
> In conclusion, I firmly believe that a fast-paced modern lifestyle can negatively affect mental health. Although modern advancements offer many benefits, people should manage their time effectively, maintain a healthy work-life balance, and prioritise their mental well-being to lead happier and healthier lives.

WE-004, page 4, full supplied answer:

> In today's modern world, the issue of whether modern life is too fast-paced for good mental health has become increasingly important. I strongly agree because it negatively affects mental well-being.
>
> One main reason is the pressure to achieve professional and financial success. Many people struggle to balance work and personal responsibilities, leading to stress, anxiety, and exhaustion. For example, employees working long hours may experience burnout and poor work-life balance.
>
> Another significant factor is social media. People often compare themselves with others, leading to insecurity and dissatisfaction. For instance, young adults comparing their lives online may feel stressed and unhappy. Excessive screen time can also reduce relaxation and meaningful communication.
>
> In conclusion, I believe a fast-paced lifestyle negatively affects mental health. Although modern advancements offer many benefits, people should manage their time effectively, maintain a healthy work-life balance, and prioritise their mental well-being.

- Verified PDF-text counts: 187 and 143 respectively, not the approximate 175
  and 135 in the remarks. Both remain clearly below the 200-word minimum.
- Reported awards: 23.69 and 22.62 out of 28. Under the currently documented
  enabled strict company policy, both should receive zero for the whole answer.
  Do not describe this strict company decision as a universal external rubric.
- This would be a deterministic policy-enforcement defect if newly evaluated
  stored inputs under the enabled policy reproduce these nonzero awards. It
  does not require asking AI to estimate the count or judging writing quality.
- Before declaring a current defect, verify evaluation timestamps against the
  policy deployment, worker versions, enabled setting and canonical text passed
  to the gate. Distinguish historical saved results from newly produced scores.
- Classification: Confirmed document-text length violations relative to current
  policy; reported historical scores not yet verified as current-policy bypasses.

### WE-005: Disagreement, Implausible Reasoning and Reported Partial Credit

- Pages 4-5; 276 words, reported 19.38/28.
- Claims include "a busy lifestyle always guarantees happiness", that continuous
  work makes people more relaxed, that people do not need sleep/holidays, that
  ignoring family brings peace of mind and that social-media comparisons never
  produce insecurity. Conclusion recommends avoiding relaxation and spending
  more time online for a stress-free life.
- The trainer calls the content entirely wrong and nonsensical. The claims are
  sweeping and internally strained, which is a meaningful argument-quality lead.
- Important distinction from SWT: If the Essay prompt permits agreement or
  disagreement, disagreeing with the expected/example position is not by itself
  an incorrect answer or grounds for zero. SWT must preserve the source's
  meaning; an opinion Essay must answer its actual task with supported reasoning.
- Assess relevance, supporting logic, development and contradictions against
  the actual prompt/rubric. Do not implement a requirement to match an essay
  model answer's stance or require automatic zero for every implausible claim.
- Without criterion breakdowns, 19.38/28 does not show whether weak argument
  marks were already deducted while language/Form criteria retained credit.
- Classification: Reported over-award for weak argument quality; score severity
  and any Content-zero requirement remain unverified.

### Writing Follow-up After Collection

- Retrieve SWT source/prompt and original result for SWT-003 first; establish
  how negative propositions were compared with the source and why Reading and
  Writing retained marks. Compare with the 76-word zero case independently.
- Retrieve exact Essay question, stored texts and criterion scores for all five
  attempts, matching the PDF labels carefully despite duplicate numbering.
- Preserve WE-003/004 results before any retry; inspect original word counts,
  strict-Form metadata, enabled setting, evaluated-at timestamps and deployment
  chronology. A new-policy result and a historical score are different findings.
- Verify SWT-001's actual rejection reason instead of inferring it from capitals.
- Compare template-labelled answers with source-specific meaning and detector
  evidence; do not turn common linking words into a hardcoded blacklist.
- Evaluate Essay stance flexibility separately from SWT source fidelity.
- No implementation, server mutations, retries or result repairs during intake.

## SST and WFD Report from Paval

- Assigned evaluator: Paval for both tasks, according to the user's assignment
  list. The document does not name the tester; creator metadata is "Abe Services".
- Received: 23 October 2026.
- Source: `/home/devaccolades/Downloads/SST and WFD .docx`, complete document text.
- Evidence: Five written SST scenarios, one cross-attempt Listening-score remark
  and one WFD scenario labelled "Attempt 2". There are no embedded images,
  tables, actual answer texts or original result screenshots.
- DOCX metadata records creation/modification on 15 October 2026. As with
  Remarks.pdf, this predates the local strict-Form policy document's 20 October
  update, but does not prove the real evaluation date or deployment state.
- Missing: Actual source audio/transcripts, candidate answers, question/paper
  names and IDs, response IDs, evaluation dates, configured criteria/maxima,
  raw/effective scores, gate metadata and deployed engine/policy versions.
- Preserve the document's "AI Evaluation" wording as the trainer's description;
  it does not prove the answer was processed by an AI engine, especially for WFD.

### SST Reported Cases

| Case | Trainer's Scenario | Reported Result | Trainer's Expected Behaviour | Evidence Status |
| --- | --- | --- | --- | --- |
| SST-001 | Answer exactly matches uploaded answer | Content 3/4 | Full Content | Written report only; uploaded reference and candidate text missing |
| SST-002 | Templated answer | "Good scores" | Whole-answer zero | No text, score breakdown or gate evidence |
| SST-003 | 75-word answer | "Good scores" | Zero for excessive length | Word count reported, not independently countable from this file |
| SST-004 | Unrelated words plus grammar/spelling errors | Good Content; full Grammar and Spelling | Deductions in all three criteria | No erroneous spans, exact marks or text supplied |
| SST-005 | Partial answer with grammar/spelling errors | Content 3/4; pooled 6/8 for Grammar, Spelling and Form | Deductions in those criteria | Individual marks/maxima and actual text missing |

### SST-001: Uploaded Answer Reportedly Receives Content 3/4

- Trainer description: "Provided correct answer which is exactly same as the
  uploaded answer."
- Result: "AI reduced score for content. It gave 3/4"; the original uses the
  fraction character for three quarters.
- Expectation: "If it is reading the uploaded answer then AI should give full
  marks for the content."
- Testable concern: If the candidate's answer faithfully and completely conveys
  the source's required points, any Content deduction should have a specific,
  evidence-based reason. Verify against the actual lecture, not only a string
  match to a model answer.
- The uploaded answer could be a source transcript, reference summary or another
  configured field. Those are not interchangeable, and matching an unverified
  reference does not independently prove full Content eligibility.
- Retrieve the exact source/reference field used by evaluation and whether any
  source material was missing or truncated. Do not declare random AI deduction,
  wrong field selection or an integrity-gate error without the stored evidence.
- Classification: Reported possible under-award; original inputs required.

### SST-002: Templated Answer Receives Unspecified Good Marks

- Trainer description: "Provided templated answer."
- Result: "AI gave good scores." Expected: "AI should gave zero for templated
  answers."
- No wording, numerical result or template/repetition assessment is supplied.
  The label alone cannot distinguish empty reusable filler from a structured
  summary containing meaningful lecture-specific points.
- Retrieve the answer and detector evidence, including actual content coverage,
  generic coverage, repetition and the configured thresholds. Do not lower
  thresholds or blacklist phrases based on this description alone.
- Classification: Reported possible template-gate bypass; insufficient evidence.

### SST-003: 75 Words Receives Nonzero Marks

- Trainer description: "Answer with incorrect form- I wrote 75 words."
- Result: "AI gave good scores." Expected: zero for excessive word limit.
- Current [company strict Form policy](STRICT_FORM_POLICY.md) allows SST 50-70
  words inclusive; a newly evaluated 75-word answer under the enabled policy
  must receive zero across the answer, not merely reduced Form marks.
- Unlike the Essay examples in Remarks.pdf, the actual text is absent here.
  The reported count cannot be independently recomputed from this document.
- Check actual stored text/count, evaluation date, strict-Form metadata, active
  setting and worker deployment version. Historical scores from before rollout
  are not evidence that the current gate is bypassed.
- Classification: Reported result conflicts with current policy if the count
  and active-policy conditions are confirmed; no verified current bypass yet.

### SST-004: Content and Language Errors Reportedly Receive Full Language Marks

- Trainer description: "Provided answers that contain few different words
  unrelated to content, grammar and spelling errors were also present."
- Result: Good Content and full Grammar/Spelling. Expected: reductions for all
  three criteria.
- Actual answer, erroneous words, corrections and numerical marks are missing.
  It is not possible to establish whether these were meaning-changing errors,
  spelling errors, acceptable variants or grammar issues without the text.
- Assess source fidelity, grammar and spelling separately. A source-inaccurate
  word may still be a correctly spelled English word; a spelling error need not
  alter every Content point. Deductions should follow each configured criterion,
  not automatically penalize every trait for a single error.
- Classification: Reported grading inconsistency; exact spans and criteria needed.

### SST-005: Partial Answer Receives Content 3/4 and Pooled Language/Form 6/8

- Trainer description: "Provided partial answer with spelling errors and grammar
  errors."
- Result: "For content it gave 3/4 and for 6/8 points for grammar, spellings and
  form." Expected: reductions in those criteria.
- Content 3/4 and pooled 6/8 already represent partial credit. The disagreement
  concerns adequacy and severity of deductions, not necessarily failure to
  deduct at all. The pooled value does not identify which criterion lost marks.
- Do not infer individual Grammar/Spelling/Form maxima or assume the 8-point
  subtotal's composition. Obtain the configured rubric and exact breakdown;
  the report's grouping may omit a trait or differ from the actual rubric.
- "Partial answer" does not quantify missing source points. Compare the retained
  meaning and omissions with the actual lecture before choosing Content marks.
- Classification: Reported possible over-award; insufficient criterion-level data.

### SST-X01: Same Listening Contribution Reported across Attempts

Trainer's full cross-attempt remark:

> In SST, I got the same listening contribution score of 6.75/9 for all the questions I attempted. This does not seem correct because different questions carry different scores.

- Reported value 6.75/9 is exactly 75%. If Content is 3/4 and the configured
  Listening maximum is 9, proportional scoring yields 3/4 x 9 = 6.75. This is
  a consistent mathematical explanation, not proof it was the actual mapping
  used on every attempt.
- Identical contributions can be legitimate for equal maxima and equal Content
  fractions; repetition of the number alone does not establish cached/fixed
  output. Conversely, if source questions really have different effective
  maxima, the same displayed denominator needs investigation.
- Separate checks: Are Content marks appropriately varied? Do the actual
  question/response snapshots have different maxima? Is the frontend showing
  the right response? Is any cache/context identity wrong? Each needs IDs.
- The claim about different question weights is trainer-reported, not verified
  configuration evidence. Do not rewrite question weights from this statement.
- Classification: Cross-attempt calibration/display/configuration lead; no
  confirmed arithmetic error. Attach to the five cases, not a sixth attempt.

### WFD-001: Three Correct Words Reportedly Credited as Two

- Source label: WFD "Attempt 2". There is no Attempt 1 in the supplied document.
- Trainer description: "Gave 3 correct words according to the audio."
- Result: "AI gave marks for 2 correct words."
- Expectation: "AI should give marks for all correct words."
- Neither the three intended words, the full submitted answer, source audio,
  configured transcript, ordering nor result breakdown is supplied.
- Current local architecture: `examinor/scoring/task_contracts.py` registers WFD
  as `EvaluationEngine.RULE`, including when an old configuration row says AI.
  This means the report's wording must not be used to blame an AI provider.
- Current implementation, `examinor/services/rule_evaluator.py`:
  `_write_from_dictation_ratio` normalizes reference/submitted words and sums
  `SequenceMatcher(..., autojunk=False)` matching-block sizes relative to the
  reference length. Feedback independently reports words "correct and in
  sequence" using the same matcher. This is an algorithm-specific sequence
  comparison, not a check that each word merely appears somewhere in the audio.
- Later inspect configured transcript accuracy, token normalization, spelling,
  repeated words, ordering and matcher behaviour. If all three eligible words
  should match, trace precisely which token is lost and where; do not assume
  an ordering difference automatically justifies losing credit without checking
  the intended WFD scoring contract.
- Distinguish matched-word count, proportional skill allocation and what the
  frontend/PDF displays. A lower skill contribution is not necessarily a lower
  matched-word count, and the report does not show which was observed.
- Classification: Reported deterministic matching/count discrepancy; reproduce
  with the exact reference/answer and deployed version before selecting a fix.

### SST and WFD Follow-up After Collection

- Retrieve SST-003 first with its actual text and result to verify the 75-word
  claim and whether strict company Form policy was active at that evaluation.
- Retrieve SST-001's reference/source and candidate answer to explain the Content
  deduction; compare all five raw Content marks and configured Listening maxima
  for the 6.75/9 concern.
- Obtain SST-002's exact template response and SST-004/005's erroneous spans,
  raw trait marks and gate evidence. Preserve examples before any reevaluation.
- Retrieve WFD-001's complete typed answer, verified source transcript/audio,
  result details and version. Reproduce matching without invoking an AI provider
  or mutating stored scores.
- No implementation, configuration edits, retries or result repairs during intake.

## Collection Complete and Verification Order

All nine requested task types now have an initial report. Repeat Sentence stays
as the user/trainer-reported working task; it has not been independently retested
in this collection. Collection completion is not fix completion or proof of all
reported defects. The records contain 45 question-level scenarios plus SST's
cross-attempt concern; several lack original inputs/results.

Proposed investigation order, not approved code changes:

1. Source fidelity: SGD-008's pets story and SWT-003's reversed meaning. Preserve
   actual source/context and results before retrying; distinguish configuration,
   request context, model assessment, gating and rendering.
2. Strict Form enforcement: WE-003/004 and SST-003. Verify input counts and
   evaluation/deployment chronology so historical scores are not mistaken for
   current-policy bypasses.
3. Transcription and delivery: RA-001/002, then disputed Fluency in RTS-004 and
   the DI/RL/SGD delivery comparisons using original audio and timing evidence.
4. Template handling and Content calibration: Compare source-specific meaningful
   answers with generic filler, preserving accepted cases and demonstrated zeros.
5. WFD word matching: Reproduce the exact three-versus-two discrepancy against
   the intended contract before changing normalization or sequencing behaviour.
6. Explanations and presentation: Gate-zero calculation wording, vague missing-
   detail feedback, the DI feedback-language issue and SST contribution display.

## Source Fidelity Implementation Status

- Authorization: User explicitly requested implementation after reviewing the
  historical evidence and today's reconstructed prompt. Initial collection-only
  restrictions no longer prohibit this scoped local implementation; no production
  result edits or historical rescoring were performed.
- Implemented: Shared independent meaning review for RL, SGD, SST and SWT,
  separate from grading/template assessments, with validated candidate/source
  quotes, source/model-bound audit cache, zero overrides and original-mark history.
- Partial/faithful summaries retain normal grading. Uncertain/invalid reviews
  return an explicit failure instead of accepting marks or inventing a zero.
- Traceability: Retained audit input snapshots/hashes, prompt version v7 in
  results and new evaluation attempts, and a non-saving server diagnostic command.
- Verification: 214 focused tests pass, including 21 new tests. Mocked regression
  reproduces a high initial Content mark/template pass followed by an off-topic
  review and checks zero skill awards in both response models/all scoring modes.
  Faithful paraphrases, partial summaries, reversed SWT, strict Form boundaries,
  invalid evidence, failures, cache separation and non-saving diagnostics covered.
- Broad suite: 424 tests, one failure/ten errors/one skip. All eleven failing
  test names reproduced on untouched HEAD (403 tests) under the same isolated
  settings. No unrelated fixes included.
- Limits: No live provider call, production deployment, PostgreSQL run or semantic
  accuracy validation completed by Codex. The separate review still depends on
  model judgment; quote validation does not prove semantic correctness.
- Scope: This source-relevance fix is implemented/tested locally, not a declaration
  that all trainer concerns are fixed. Original SingleResponse 289 is unchanged.
- Details and deployment notes: [Source Fidelity Policy](SOURCE_FIDELITY_POLICY.md).

## Next Evidence

**SGD-008 is located as SingleResponse 289, question 680 (BB-SGD 1), Bindu-T2.**
Its stored evaluation, current PE reference and historical job/attempt/cache
metadata have been inspected. Those records do not retain the original source
or prompt. Today's prompt reconstruction has confirmed candidate/reference
inclusion and explicit relevance instructions, without calling a provider.
After deploying the scoped fix, run `check_response_source_fidelity` for single
response 289, first dry-run then with explicit `--evaluate`, to inspect the live
reviewer without response/cache writes. Also check a faithful PE answer. Then
agree on any end-to-end replay or historical repair separately; do not overwrite
the original response to obtain a passing result.
Continue one case at a time; server evidence was deferred during report intake
and is the next phase, not an implied authorization to change production data.

## Detailed Case Record Format

Use one record per submitted evaluation. Attach later evidence to the same
record when it concerns the same response; do not count it as a new case.

### Case ID: [task abbreviation and sequence]

- Task type and assigned evaluator:
- Date received:
- Question ID/name:
- Response ID and session ID, if available:
- Full exam or single-question practice:
- Evaluation date, scoring mode, model/policy version, if known:
- Evidence supplied: screenshots, PDF pages, audio, transcript or server output.

#### Question and Candidate Response

- Actual prompt and required image/audio/source:
- Candidate's original answer or recording:
- Stored transcript, if applicable:
- Any missing or disputed input:

#### Observed System Result

- Criterion scores and maxima:
- Skill contributions or final score, if provided:
- Feedback and highlighted errors:
- Gate/override evidence, if available:

#### Trainer Feedback

- Verbatim concern or observation:
- Expected behaviour or score, as stated by the trainer:
- Supporting explanation, if supplied:

#### Our Assessment

- Evidence-based observations:
- Applicable rubric or company policy:
- Classification: confirmed issue / suspected issue / expected behaviour /
  insufficient evidence.
- Likely affected layer, only if supported: source configuration, transcription,
  AI assessment, integrity gate, score calculation, display/PDF or other.
- Confidence and reasoning:
- Evidence still needed:

#### Deferred Fix and Acceptance Case

- Candidate correction, not yet implemented:
- Expected behaviour to verify:
- Working behaviour that must remain unchanged:
- Decision: pending joint review.
