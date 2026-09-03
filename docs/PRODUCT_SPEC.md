# Ion OS — Master Product & Engineering Specification

> Canonical source transcription generated from the uploaded PDF. Page markers are preserved for traceability. The PDF remains the source artifact; this Markdown copy exists so local coding agents can read the specification reliably.
>
> **The transcription is preserved verbatim and is not edited in place.** Owner-approved amendments are appended at the end of this document and supersede the passages they name. Read them before relying on any rule above — several early passages have been superseded by decisions made during real acceptance testing.


---

## PDF Page 1

Ion OS — Master Product & Engineering
Specification
Version: 0.1
Status: Product architecture baseline
Primary platform: macOS
Secondary platform: mobile companion
Core principle: Local-first personal operating system with selective AI augmentation
1. Product Vision
Ion OS is a private, local-first personal operating system designed to centralize, understand, organize, and
help act on the user's life information.
Ion combines:
tasks;
assignments;
calendars;
email;
courses;
grades;
studying;
projects;
research;
career opportunities;
job and internship applications;
graduate-school preparation;
goals and milestones;
knowledge and notes;
books, movies, games, and other media;
personal writing;
finances;
focus sessions;
daily reviews;
longitudinal behavioral analytics.
Ion should reduce manual organization rather than create another system the user must constantly
maintain.
The guiding workflow is:
Capture → Understand → Connect → Plan → Execute → Review → Adapt
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
1


---

## PDF Page 2

Ion is not intended to replace the user's thinking. It should reduce administrative overhead, surface
relevant information, identify conflicts and patterns, make recommendations, and carry out explicitly
authorized actions.
2. Product Principles
2.1 Local first
The authoritative Ion database should live on the user's Mac.
Core functionality should continue without a cloud server .
Local data includes:
structured Ion database;
Obsidian knowledge vault;
task history;
analytics;
goals;
project information;
cached integration data;
local embeddings/search indices;
settings;
permitted financial information.
Cloud services are integrations, not Ion's primary datastore.
2.2 AI is not the database
The LLM must never become Ion's memory system.
Ion retrieves relevant structured/local information and gives the model only the context necessary for the
current task.
Ion database
     ↓
Local retrieval
     ↓
Context filtering
     ↓
AI model
     ↓
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
2


---

## PDF Page 3

Suggested/structured result
     ↓
Ion validates + stores result
2.3 User data is not product configuration
Current user goals, tasks, courses, companies, universities, budgets, interests, and priorities must not be
hardcoded into Ion's source code, prompts, or product specification.
They are runtime records.
The public repository must contain synthetic example records instead.
Example:
WRONG
if userGoal == "ML internship":
    prioritizeMachineLearning()
CORRECT
goal = database.getActiveGoals()
priority = planningEngine.evaluate(goal)
This prevents today's priorities from permanently biasing future Ion behavior .
2.4 Human actions outrank agent actions
A direct human change overrides an automated Ion decision.
If the new action creates problems, Ion should surface a recommendation rather than silently reversing the
user .
2.5 Summary first, detail on demand
Ion should rarely display all of its internal metrics.
A task should initially appear approximately as:
3


---

## PDF Page 4

CSE Project
Due tomorrow · ~2h remaining
rather than:
Urgency 91 · Importance 84 · Cognitive Load 8.1 · Confidence 77% · Goal Affinity .86
Detailed reasoning remains accessible through controls such as:
Why?
and, when uncertainty matters:
Uncertain
3. Core Information Architecture
Permanent primary navigation:
Home
Today
Calendar
Projects
School
Career
Knowledge
Library
Secondary features are accessed contextually or through navigation/search rather than creating excessive
permanent pages.
Examples:
Daily Review → Today
Weekly Reset → Home / Calendar
Insights → contextual
Analytics → contextual Insights
Grad School → Career subsection initially
Finance → Area / secondary destination
Research → surfaced in Projects, Career , Grad School, and Knowledge as appropriate
Settings → system control
Ask Ion → global action
Capture → global action
1. 
2. 
3. 
4. 
5. 
6. 
7. 
8. 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
4


---

## PDF Page 5

4. Canonical Data Model
Ion should follow:
one canonical record → multiple contextual views
An object should not be duplicated because several sections need to display it.
Example:
Research Experience
UW Research Lab
       │
       ├── Projects view
       ├── Career view
       ├── Grad School view
       ├── Knowledge view
       └── Research view
All views resolve back to the same underlying object.
5. Core Entity Types
Initial domain entities should include:
Personal organization
Area
Goal
Milestone
Skill
Task
TaskGroup
CalendarBlock
Deadline
Routine
FocusSession
DailyReview
WeeklyPlan
Decision
Insight
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
5


---

## PDF Page 6

School
Course
Syllabus
Assignment
Assessment
Grade
AcademicConcept
StudySession
CourseResource
Projects
Project
ProjectMilestone
ProjectIdea
ProjectDecision
ProjectResource
Repository
Research
ResearchExperience
ResearchProject
ResearchOutput
ResearchPaper
ResearchIdea
ResearchOpportunity
ResearchSkill
ResearchContact
Research objects belonging to the same lab/project should be grouped beneath the same high-level
research experience rather than appearing as unrelated records.
Career
Opportunity
Application
Company
Contact
ResumeVersion
CoverLetterVersion
InterviewStage
ProfessionalGoal
Graduate school
Program
University
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
6


---

## PDF Page 7

Faculty/Lab
Requirement
Application
ApplicationComponent
PreparationArea
Evidence
ReadinessAssessment
Knowledge
KnowledgeNode
Source
Note
Capture
Attachment
KnowledgeGap
Relationship
Library
Book
Movie
TVSeries
Game
Article
Paper
Course
Website
Artwork
UserWriting
UserPhotography
UserDrawing
Finance
AccountSummary
Transaction
Income
Expense
Subscription
Budget
SavingsGoal
InvestmentRecord
TaxRecord
CreditMetric
FinancialScenario
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
7


---

## PDF Page 8

6. Relationship System
Ion should not permanently link everything to everything.
Three relationship layers are required.
6.1 Structural
Strong, explicit, durable relationships.
Examples:
Assignment → Course
Task → Project
Project → Goal
Application → Opportunity
ResearchExperience → GradSchoolPreparation
Milestone → Skill
Displayed normally in Ion.
6.2 Contextual
Valid relationships useful in some contexts but not important enough to dominate the graph.
Example:
Article ~ Project
Course note ~ Skill
Book ~ Interest
Research paper ~ Graduate program
Usually hidden unless relevant.
6.3 Soft/inferred
Relationships calculated by search/embeddings/AI.
Example:
8


---

## PDF Page 9

These notes discuss related approaches to visualization.
Soft links should not automatically become permanent user relationships.
Only the most relevant approximately 3–5 relationships should initially appear on an entity.
A View all connections action exposes the rest.
7. Ion Core Visualization
The Ion Core is the visual identity of the desktop application.
It is an interactive spherical network visualization positioned in the upper center of Home.
Approximate size:
28–33% of the initial viewport height
Visual direction:
nearly solid black background;
subtle bloom surrounding the sphere;
dense electric-purple network;
thousands of small points/edges when data size permits;
high information density inspired by the provided references;
no permanent labels while dormant;
restrained blue/teal secondary accents;
soft white typography.
Where technically reasonable, visible nodes should map 1:1 to Ion records until the graph becomes too
large for meaningful/performance-safe representation.
Density itself should communicate connectivity.
Highly connected areas appear visually denser .
Sparse areas appear less developed.
The sphere should:
continuously rotate subtly;
pulse;
react to Ion state;
support 360° user rotation;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
9


---

## PDF Page 10

support zoom;
allow click-to-scope;
physically rotate toward selected clusters;
zoom into that cluster;
reveal labels after the user deliberately explores it.
The default visualization is aesthetic/ambient.
An explicit Explore mode enables deeper graph navigation.
8. Core State Visualization
The Ion Core reflects system state.
Idle
Slow rotation and subtle pulses.
Processing
Activity travels through relevant connections.
Urgent state
Slight increase in intensity without turning the interface red or alarming.
Focus mode
Motion becomes calmer and dimmer .
Deep Ask
Relevant region becomes illuminated.
Offline
Core remains operational; remote state is communicated separately.
Future voice support
Core may react subtly to speech amplitude.
Voice is not an initial development priority.
• 
• 
• 
• 
• 
10


---

## PDF Page 11

9. Home
Home should remain restrained.
It contains:
Ion Core;
Focus;
Needs Attention;
small Upcoming preview;
Ask Ion control.
It should not replicate the entire Today page.
10. Today
Today is the operational dashboard.
Desktop uses split view.
Left
top priorities;
tasks;
backups if capacity becomes available;
deadlines;
focus controls;
relevant suggestions.
Right
current-day timeline;
calendar;
upcoming blocks;
available time.
The interface should communicate what matters without exposing internal complexity by default.
11. Calendar
Google Calendar is the authoritative scheduled-time source.
Ion maintains true two-way synchronization.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
11


---

## PDF Page 12

Changes in Ion update Google Calendar .
Changes in Google Calendar update Ion.
Multiple calendars appear in one unified calendar but remain visually distinguishable.
Use a restrained color system:
violet family;
blue-violet;
teal;
muted lavender;
brighter electric purple for Ion-created focus blocks.
Categories such as:
academic;
work;
meals;
health;
personal;
Ion focus;
should remain distinguishable without creating a rainbow interface.
Events have flexibility metadata:
Locked
Examples:
class;
work;
appointments.
Flexible
Examples:
gym;
study;
personal projects.
Ion-controlled
Blocks created specifically by Ion.
Ion may not modify locked events without explicit confirmation.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
12


---

## PDF Page 13

If email or another source indicates a real work/class schedule change, Ion should detect it and propose the
modification.
Potentially suspicious changes require confirmation.
12. Deadlines vs. Calendar Blocks
A deadline is not a calendar appointment.
Example:
Assignment deadline
Friday · 11:59 PM
Ion separately creates work blocks leading to the deadline.
The task remains open until completion regardless of the number of scheduled work blocks.
13. Task Model
Tasks can originate from:
Canvas;
Gmail;
projects;
goals;
weekly planning;
user capture;
AI suggestions;
recurring systems.
Ion should attempt to know the majority of consequential tasks automatically.
The user should primarily need to add personal or unusual tasks.
Tasks have:
state;
source;
urgency;
importance;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
13


---

## PDF Page 14

estimated duration;
progress;
deadline;
related goal/project/course;
scheduling constraints;
completion evidence.
Urgency and importance remain separate.
14. Assignment Decomposition
All Canvas assignments should be imported.
Ion analyzes each assignment.
Not every assignment requires decomposition.
For a sufficiently complex assignment:
Parent Assignment
◈ Broken into 4 steps
Understand requirements
Implementation
Testing
Final review/submission
Subtasks remain visibly grouped beneath the parent.
Ion should suggest decomposition rather than blindly create numerous unnecessary tasks.
15. Duration Prediction
Initially the user may provide:
expected duration;
percentage of a study block allocated to the task;
estimated progress.
• 
• 
• 
• 
• 
• 
• 
• 
• 
14


---

## PDF Page 15

Ion subsequently learns from:
predicted time;
actual focus time;
assignment type;
subject;
difficulty patterns;
historical estimation error;
completion percentage.
Example:
Initial estimate     2h
Ion estimate         2h 35m
Actual               2h 29m
Historical models should weight recent behavior more strongly while also recognizing seasonal workload
patterns.
16. Scheduling Engine
Weekly planning primarily occurs Sunday evening.
Ion automatically collects:
Canvas deadlines;
calendar commitments;
assignments;
unfinished work;
relevant Gmail actions;
projects;
goals;
routines;
historical duration estimates;
available hours;
workload;
recent energy/focus patterns.
Ion creates a proposed week.
The user reviews consequential changes.
Approved blocks are written to Google Calendar .
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
15


---

## PDF Page 16

If requested work exceeds available time, Ion must say so.
Example:
You have approximately 5 usable hours but this plan requires 9.
Move ML study later or change an existing commitment?
Ion should not obediently create impossible schedules.
When a block goes unfinished, Ion initially proposes a new slot and asks before changing Google Calendar .
With enough confirmed behavior , selected actions may become whitelisted.
17. Minimum Viable Progress
Long-term goals/projects can define:
ideal weekly progress;
minimum viable progress.
Minimum progress should be distributed intelligently across days rather than deferred entirely until the end
of the week.
18. Focus System
Focus mode should support:
Momentum;
Pomodoro;
Deep Work;
Custom;
future Adaptive mode.
Momentum mode is important.
Ion must not forcibly interrupt productive momentum because a timer ended.
A break can become available rather than mandatory.
Focus screen should be intentionally sparse.
Typical display:
• 
• 
• 
• 
• 
• 
• 
16


---

## PDF Page 17

Project / Assignment
43:18
Ion Core — calm state
1 of 3 objectives
Pause      Finish
Break available
Cognitive-cost estimates operate in the background and should not normally be displayed unless the user
asks.
19. Canvas / Academic System
Ion imports:
assignments;
due dates;
grades/scores;
syllabi;
important announcements;
relevant modules;
meaningful files/resources;
calendar changes;
urgent course changes.
Most Canvas information may be stored, but notifications should be selective.
At the start of a term, Ion builds a course profile containing:
instructor;
syllabus;
grading breakdown;
exam dates;
late policy;
office hours;
textbook/resources;
current standing;
target performance.
Ion independently verifies that assignments are properly submitted in Canvas.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
17


---

## PDF Page 18

Submission completes the submission portion of an assignment but does not falsely mark all associated
study work complete.
20. Studying and Academic Understanding
Studying is tracked independently of homework.
A student may:
finish all homework;
still need conceptual review.
Each course can contain an Understanding / Concept Map.
Possible stages:
Introduced → Practicing → Applied → Strong → Continuing
Evidence may come from:
grades;
mistakes;
study sessions;
notes;
assignment results;
self-assessment;
quizzes;
discussion with Ion.
Weak areas should be surfaced when useful for improving academic performance.
21. Grade Forecasting
Ion may calculate:
current grade;
category weighting;
expected final outcomes;
remaining grade requirements;
strategic importance of upcoming assessments.
It should avoid false precision.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
18


---

## PDF Page 19

22. Gmail
Ion connects to:
school Gmail;
primary personal Gmail;
secondary/low-priority personal Gmail.
Default processing strategy:
retrieve metadata;
determine likely relevance;
retrieve message body selectively when useful.
Marketing/promotion messages can be locally classified.
High-confidence irrelevant marketing can eventually be archived automatically according to permitted
rules.
Consequential email changes remain reviewable.
Ion should support:
inbox intelligence;
important-message detection;
deadline extraction;
action detection;
schedule-change detection;
email → task creation;
source relationships;
email cleanup;
future automatic archival rules;
draft generation.
Ion never sends an email without user approval.
Tasks derived from email retain a source link to the original thread.
23. Email Cleanup
Ion should support cleanup analysis such as:
Likely newsletters
Promotional
• 
• 
• 
1. 
2. 
3. 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
19


---

## PDF Page 20

Receipts
Notifications
Important personal
Bulk operations require approval initially.
The system may later learn rules such as:
Archive shipping notifications after 30 days.
Corrections should prompt:
Remember this preference?
One correction does not silently create a permanent rule.
24. Projects
Project lifecycle:
Idea → Exploring → Planned → Active → Paused → Completed → Archived
Optional:
Abandoned
Abandonment is not treated as failure.
Projects screen displays large enough entries to communicate:
description;
current progress;
next step;
current milestone;
what is required to continue/start;
skills being developed;
skills needing strengthening;
status;
recent activity.
Completed projects retain:
Built From;
Led To;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
20


---

## PDF Page 21

relationships so ideas can evolve into future projects.
25. Project Planning Agent
For a new project idea, Ion can propose:
purpose;
usefulness;
originality;
required knowledge;
existing skills;
skills to develop;
datasets/resources;
architecture;
milestones;
tasks;
portfolio value;
future extensions.
User approval turns proposed plans into active intentions.
Rejected AI suggestions do not become user goals.
26. GitHub
GitHub is a first-class project integration.
Initial target: Level 2 integration.
Track:
repositories;
commits;
activity;
README status;
issues;
milestones;
pull requests;
project relationship.
Ion should also function as a portfolio-maintenance assistant.
Examples:
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
21


---

## PDF Page 22

README has not been updated since the latest major feature.
This project is portfolio-ready but has no screenshots.
Repository has no clear setup instructions.
Add a demo before marking this project complete.
The long-term objective is a professional, highly presentable GitHub profile rather than merely maximizing
contribution counts.
27. Career
Career contains three major zones:
Opportunities
Internships, jobs, research opportunities and relevant programs discovered by Ion.
Applications
Application pipeline and associated materials.
Development
Professional goals, skills, projects, GitHub readiness, portfolio readiness and long-term preparation.
Ion should continuously search for relevant opportunities.
Opportunities should use interpretable labels such as:
Strong Fit;
Worth Exploring;
Lower Priority;
rather than fabricated precision like "92.4% match."
A Why? view explains reasoning.
• 
• 
• 
22


---

## PDF Page 23

28. Applications
Application entity includes:
organization;
role;
location;
deadline;
source;
status;
application date;
contacts;
interview stages;
follow-up date;
related skills;
job description snapshot;
resume version;
cover-letter version;
relevant notes.
Ion should replace a separate application spreadsheet.
29. Resume Management
Ion tracks multiple resume versions.
Resume variants may be:
general;
ML;
analytics;
SWE;
policy;
role-specific.
Applications preserve the exact resume version used.
Support Overleaf/LaTeX-oriented workflow where technically practical.
Ion should help identify:
stale resumes;
inconsistent versions;
applications lacking tailoring;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
23


---

## PDF Page 24

stronger evidence that should be added to future versions.
30. Graduate School
Graduate-school planning is a dedicated Career subsystem and may later become a first-class page.
Ion should:
discover target programs;
store programs and deadlines;
understand published prerequisites;
identify relevant faculty/labs;
analyze alignment;
track research preparation;
track academic preparation;
track technical preparation;
track professional evidence;
track application components;
recommend high-leverage actions.
Rather than inventing an admission percentage, Ion should use qualitative evidence-based readiness
classifications such as:
Reach;
Developing;
Competitive;
Strong;
with uncertainty clearly communicated.
The system should continuously compare current progress with target-program expectations and help
steer coursework, research, projects, professional development and applications accordingly.
Research should be surfaced as evidence inside graduate-school preparation without duplicating research
records.
31. Research
Research is a first-class domain.
Types include:
Research Experience;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
24


---

## PDF Page 25

Research Project;
Research Paper;
Research Idea;
Research Opportunity;
Research Skill.
When multiple outputs occur under one lab or research experience, group them under the same umbrella.
Example:
Research Lab
├── Application/outreach
├── Project A
├── Project B
├── Papers
├── Skills
├── People
└── Outputs
Research may appear contextually in:
Projects;
Career;
Grad School;
Knowledge;
Applications.
These are views of the same records.
32. Goals and Progression
Goals may include:
Outcome;
Skill;
Habit;
Project;
Academic;
Personal.
Progression should not rely on arbitrary percentages for knowledge.
Use adaptive stages:
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
25


---

## PDF Page 26

Foundation → Developing → Applied → Strong → Continuing
A visual bar communicates progression between stages.
Skills can be hierarchical.
Example:
Professional Development
└── UI/UX Development
    ├── Visual Design
    ├── React UI
    └── Interaction Design
Ion should avoid creating hundreds of tiny permanent skill objects.
New interests can be suggested as subsections of broader existing areas.
Completed milestones lead naturally to suggested next milestones.
33. Knowledge System + Obsidian
Ion is the primary interface.
Obsidian is the durable knowledge-storage layer .
The user should not need to manually configure or maintain an elaborate Obsidian system.
Suggested vault structure:
Inbox/
Knowledge/
Projects/
Courses/
Research/
Library/
Journal/
Daily Reviews/
Decisions/
Sources/
26


---

## PDF Page 27

Ion may automatically:
create folders;
create notes;
create tags;
create high-confidence links.
Initially ask before:
renaming;
moving;
deleting.
34. Raw Inbox
Raw Inbox exists to support:
capture now → organize later
Possible captures:
website;
screenshot;
handwritten note;
project idea;
class material;
recipe;
article;
book;
movie;
Canvas information.
Capture should require very little categorization.
Local processing can later:
classify;
extract text;
identify relationships;
create companion notes;
suggest projects/tasks;
flag uncertainty.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
27


---

## PDF Page 28

35. Knowledge vs. Sources
Ion explicitly distinguishes:
Source information
"What the source says."
Personal knowledge
"What the user understands, concludes, or creates."
A PDF can have an associated Markdown companion note containing:
citation/source;
summary;
key ideas;
concepts;
personal notes;
related knowledge;
related projects;
questions;
knowledge gaps.
The original PDF is preserved.
36. Knowledge Gaps
Ion can identify gaps using evidence from:
coursework;
projects;
notes;
quizzes;
self-assessment;
GitHub activity;
mistakes;
completed milestones.
Avoid fabricated precision.
Evidence should be inspectable.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
28


---

## PDF Page 29

37. Search
Two systems coexist.
Fast deterministic search
Triggered by ⌘K.
Searches:
projects;
courses;
tasks;
notes;
files;
applications;
knowledge;
library.
No LLM required.
Conversational search
Example:
Why haven't I made progress on the policy project?
Uses AI after locally retrieving relevant evidence.
38. Ask Ion
Ion should not look like a ChatGPT clone.
A prominent Ask Ion button opens a compact input.
Short results appear in place.
Long discussions can open a dedicated conversation workspace.
The UI should indicate when a request is local versus Cloud Deep Ask.
• 
• 
• 
• 
• 
• 
• 
• 
29


---

## PDF Page 30

39. Daily Review
Daily Review supports prompts:
What got done?
What didn't?
Energy/burnout?
Focus?
Any priority changes?
The user may instead write freely.
Ion locally extracts structured information and asks for confirmation where appropriate.
Daily review updates:
task progress;
scheduling;
energy patterns;
planning assumptions;
priority changes;
insights.
Low energy reported after a failed day can influence future planning without rewriting the past schedule.
40. Longitudinal Analytics
Ion analyzes:
completion patterns;
estimation error;
focus sessions;
time of day;
energy;
sleep when available;
workload seasonality;
task deferrals;
project progress;
academic understanding.
Recent history receives stronger weighting while seasonal patterns remain available.
Insights should be narrative first.
Example:
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
30


---

## PDF Page 31

You complete math sessions more consistently when they begin before 4 PM.
Relevant charts can be shown underneath.
41. Stale Commitments
Repeatedly deferred tasks trigger review.
Example:
You've moved this task four times.
Options:
Still important;
Lower priority;
Pause;
Remove.
42. Decisions
Ion stores important decisions with basic reasoning.
Example:
Decision
Use Obsidian as Ion knowledge layer
Reason
Portable local Markdown
Date
...
Related
Ion architecture
Ion can later remind the user why the decision was made.
• 
• 
• 
• 
31


---

## PDF Page 32

43. Library
The backend uses a unified library schema.
The UI visibly separates:
Books;
Movies;
TV;
Games;
Articles/Papers;
other categories.
Track where relevant:
want to consume;
currently consuming;
finished;
abandoned;
rating;
dates;
progress;
source;
related projects.
Existing spreadsheets should be importable.
Library recommendations may consider:
ratings;
current interests;
goals;
saved items;
recent consumption;
available time.
Media should only receive strong knowledge links when highly relevant.
Other relationships remain soft.
44. Finance
Finance is a private-local Ion area.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
32


---

## PDF Page 33

Initial data sources:
manual entries;
existing spreadsheet imports;
bank/card CSV exports;
permitted receipt/order email metadata;
recurring expenses.
Do not initially require direct banking credentials.
Track:
balances;
income;
spending;
recurring expenses;
subscriptions;
budgets;
savings;
investment records;
taxes;
credit metrics;
financial goals.
Financial actions remain advisory.
Ion does not:
execute payments;
buy investments;
transfer money;
make purchases.
45. Financial Scenarios
Ion supports questions such as:
Can I afford this purchase?
Output may include:
purchase price;
projected post-purchase balance;
budget impact;
savings-goal delay;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
33


---

## PDF Page 34

emergency reserve impact;
recurring-cost impact.
It should also model saving/investing scenarios.
Financial calculations should use deterministic mathematics wherever possible rather than relying on an
LLM.
46. Financial Privacy
Data classes:
Normal
Tasks, projects, calendar , etc.
Private Local
Financial information.
Private Local information may be processed locally but is never automatically included in Cloud Deep Ask.
Forbidden
Do not store:
SSN;
card number;
CVV;
banking password;
account PIN;
authentication tokens;
API keys;
private keys;
passwords.
47. Sensitive Information Filter
All ingested data passes through a deterministic local sensitive-information/secret detector before indexing
or model use.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
34


---

## PDF Page 35

Input
  ↓
Sensitive-data scanner
  ├─ prohibited → do not store
  └─ acceptable → continue
If prohibited data is detected:
Sensitive information detected.
This value was not stored.
Save a redacted version instead?
The raw secret should not be preserved.
No detector can guarantee perfect identification, so the user is additionally encouraged not to upload
secrets intentionally.
48. AI Architecture
Ion uses a provider abstraction.
Ion Feature
    ↓
AI Router
    ├── Local Provider
    ├── OpenAI Provider
    ├── Anthropic Provider
    └── future providers
No feature should directly depend on a specific AI vendor .
49. AI Tiers
Tier 0 — No AI
Preferred wherever possible.
Examples:
calendar synchronization;• 
35


---

## PDF Page 36

finance calculations;
task state;
urgency calculations;
progress statistics;
focus timers;
GitHub metrics;
exact search.
Tier 1 — Local AI
Default routine intelligence.
Potential implementation:
Ollama + suitable local model.
Use for:
classification;
basic extraction;
note organization;
daily-review parsing;
assignment interpretation;
local summaries;
relationship suggestions.
Tier 2 — Cloud Deep Ask
Opt-in frontier-model reasoning.
Use for:
complex project planning;
major weekly tradeoffs;
deep knowledge-gap analysis;
graduate-school analysis;
complex research/career reasoning;
sophisticated long-document synthesis.
50. Cloud AI Budget
Cloud AI is disabled or conservative by default.
User can configure a monthly budget, initially approximately:
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
36


---

## PDF Page 37

$5–10/month
Ion tracks:
provider;
model;
input tokens;
output tokens;
approximate cost;
purpose;
timestamp.
Large Deep Ask requests should display estimated cost when appropriate.
Example controls:
Local · Fast · Deep · Max
Ion performs retrieval locally before sending cloud context.
51. Cloud Context Minimization
Before Deep Ask:
User request
   ↓
Local retrieval
   ↓
Relevant records only
   ↓
Sensitive-data filter
   ↓
Private-local exclusion
   ↓
Context summary
   ↓
Cloud model
Journal, finance, unrelated emails, credentials and unrelated notes should not leave the Mac by default.
• 
• 
• 
• 
• 
• 
• 
37


---

## PDF Page 38

52. Agent Personality
Ion uses an adaptive Advisor/Coach model.
Usually:
concise;
advisory;
proactive when helpful.
More challenging behavior appears when appropriate.
Example:
Tomorrow's plan needs about 9 hours. You have 4.5 available.
When explicitly asked to think something through, Ion becomes more conversational and analytical.
53. Agent Modes
Potential modes:
Normal;
Focus;
Planning;
Review;
Explore;
Private.
Private Mode disables external AI.
54. Notifications
Notification classes:
Critical;
Important;
Planning;
Suggestion;
Insight.
Insights are normally checked deliberately unless user enables insight notifications.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
38


---

## PDF Page 39

Ion uses an attention budget so ordinary suggestions do not create constant interruptions.
Urgent events bypass that limit.
Back-up tasks can be surfaced when extra capacity becomes available.
55. Confidence
Confidence should only become visible when uncertainty matters.
Small Uncertain indicator opens a modal explaining:
what is uncertain;
evidence;
possible actions.
56. Explainability
Planning recommendations can expose a hidden:
Why?
Example:
Why Tuesday 2–4?
• assignment due Wednesday
• estimated 1h 45m
• strong recent focus window
• 20m safety buffer
57. Automation Authority
Three conceptual levels:
Read
Ion observes.
• 
• 
• 
39


---

## PDF Page 40

Propose
Ion recommends actions.
Automated
Specific whitelisted actions execute automatically.
Initial behavior should usually be:
Read + Propose
The system gradually learns which low-risk actions the user permits.
Consequential changes remain confirmable.
58. Audit Trail
Every meaningful automated action is logged.
Example:
12:04 Imported Canvas assignment
12:04 Updated urgency
12:05 Suggested schedule change
12:07 User approved
12:07 Google Calendar updated
AI suggestions do not become user intentions until accepted.
59. Undo + Recovery
Almost all reversible actions provide Undo.
Examples:
email archived;
task moved;
calendar changed;
link created.
• 
• 
• 
• 
40


---

## PDF Page 41

Deletion uses Trash.
Default retention:
approximately 30 days.
AI may never permanently delete user-created information without explicit approval.
60. Version History
Important text/state objects retain revision history where practical:
notes;
projects;
goals;
weekly plans;
decisions;
resumes.
61. Integration Failure Rules
Ion must never invent fresh integration information when an API is unavailable.
Cached information may continue to be used.
Only show stale-data indicators when the delay could meaningfully affect decisions.
Failed writes preserve the last confirmed authoritative state.
Example:
Calendar update failed. Original schedule preserved.
Provide Retry.
62. Conflicting Sources
When sources disagree, Ion should surface the conflict.
Example:
• 
• 
• 
• 
• 
• 
41


---

## PDF Page 42

Canvas       Friday 11:59 PM
Syllabus     Thursday
Default conservative recommendation:
Treat Thursday as the safe deadline until confirmed?
63. Offline Mode
Without internet, Ion continues supporting:
tasks;
projects;
notes;
library;
local search;
local AI;
focus;
analytics;
cached calendar;
cached academic information.
Integrations sync automatically after reconnection.
64. Mobile Companion
Mobile falls between companion-only and full parity.
Initial mobile capabilities:
Today;
Tasks;
Calendar;
Capture;
Ask Ion;
Focus;
Daily Review;
notifications;
Library quick-add;
Project quick-view.
The full WebGL Ion Core is not required on mobile.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
42


---

## PDF Page 43

Mobile prioritizes usability and battery life.
Basic tasks/calendar information should remain accessible even when the Mac is unavailable through an
appropriate cached/synchronized architecture.
65. macOS Experience
Ion runs quietly in the background when enabled.
Menu-bar icon appears near standard macOS status controls.
Compact menu may show:
ION
3 priorities remaining
Next
Study · 4:00 PM
Start Focus
Quick Capture
Ask Ion
────────────
Open Ion
A global Quick Capture shortcut should open a minimal overlay without requiring the full app.
66. UI Design Language
Ion is intentionally dark-first.
Foundation:
nearly black background;
charcoal secondary surfaces;
off-white text;
electric violet primary energy;
restrained indigo/blue;
limited teal.
• 
• 
• 
• 
• 
• 
43


---

## PDF Page 44

Purple primarily dominates:
Ion Core;
active interactions;
selected states;
focus blocks;
important motion.
Approximately:
95% black/neutral environment, 5% high-impact energy color
rather than flooding the UI with gradients.
67. Glass
Glassmorphism is intentionally limited.
Use primarily for:
suggestions;
temporary overlays;
command palette;
modals;
expanded details;
Ask Ion;
menu-bar panels.
Routine lists should usually rely on typography, spacing and subtle rules rather than glass cards.
68. Typography
Direction:
technical + premium + editorial
Avoid stereotypical sci-fi fonts.
Use:
strong modern sans;
clean hierarchy;
restrained metadata;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
44


---

## PDF Page 45

high readability;
no dependency on uppercase system labels.
69. Navigation
Desktop:
thin left icon rail;
icons only by default;
expands temporarily on hover;
command palette through ⌘K.
Ask Ion has a visible UI control rather than requiring memorization of another keyboard shortcut.
70. Motion
High-value motion:
Ion Core;
graph scope transitions;
contextual suggestions;
task expansion;
progress transitions;
calendar scheduling;
focus states;
navigation;
command palette.
Avoid:
scroll hijacking;
particle systems everywhere;
excessive blur;
decorative animation with no purpose.
Ion should reduce animation when:
app is backgrounded;
battery-saving behavior is appropriate;
Focus Mode is active;
reduced-motion accessibility is enabled.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
45


---

## PDF Page 46

71. Sunday Weekly Reset UI
Dedicated interactive planning workspace.
Possible layout:
Left
Unplaced/new responsibilities.
Center
Weekly calendar .
Right
Ion analysis.
Ion automatically imports assignments/tasks first.
The user primarily verifies rather than manually rebuilding the week.
Manual drag/drop remains available.
Ion detects overscheduling during manual changes and proposes adjustments.
72. Suggestions
Three UI levels:
Toast
Informational confirmation.
Floating suggestion
Recommendation requiring optional action.
Blocking confirmation
Consequential or unusual change.
46


---

## PDF Page 47

73. Projects UI
Default projects page groups by project status.
Cards/rows should be somewhat larger than standard compact task cards so useful tracker information can
be seen without entering every project.
Primary project detail priorities:
progress;
next step;
what is required to continue;
skills/areas being strengthened;
areas the project develops;
milestones;
context necessary to understand the project.
The user should be able to understand projects even if an AI coding agent generated much of the
implementation.
74. School UI
School should be a more optimized command center than Canvas.
Each current course initially shows only important information:
current standing;
next deadline;
workload;
understanding gaps;
exam schedule;
notes access;
useful summaries.
Course detail contains deeper academic information.
75. Career UI
Career includes:
Opportunities;
Applications;
1. 
2. 
3. 
4. 
5. 
6. 
7. 
• 
• 
• 
• 
• 
• 
• 
• 
• 
47


---

## PDF Page 48

Development;
Research;
Grad School.
Research and Grad School can expand in prominence as the system develops.
76. Knowledge UI
Knowledge should support at least two modes:
Progression
Areas → goals → skills → milestones.
Knowledge Map
Concepts and meaningful relationships.
The exact visual combination should be refined through prototyping rather than locked prematurely.
77. Library UI
Library may be more visual than productivity sections.
Use:
covers;
posters;
artwork;
clean category navigation.
This is an appropriate place for more expressive visual presentation.
78. Insights
No permanent global Analytics dashboard is required initially.
Insights appear contextually.
• 
• 
• 
• 
• 
• 
• 
48


---

## PDF Page 49

Examples:
School Insights;
Career Insights;
Project Insights;
Financial Insights;
Focus Insights.
Global Insights can still be located through command search.
Narrative precedes charts.
79. Backups
Use two backup strategies.
Local
Automatic local backup/versioning.
Selective iCloud
Prioritize small critical information:
database;
Markdown;
settings;
projects;
goals;
task history.
Large recoverable files should not unnecessarily consume iCloud storage.
Avoid duplicating data easily recoverable from Google, Canvas, GitHub, etc.
80. Secrets
Credentials required by Ion must be stored through macOS Keychain or equivalent secure OS credential
storage.
Never store secrets in:
source code;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
49


---

## PDF Page 50

Git;
Obsidian;
SQLite plaintext user records;
documentation.
Repository contains only configuration examples.
81. Proposed Technical Architecture
Subject to prototyping.
Desktop
React + TypeScript
Desktop shell
Tauri
Backend/application logic
Python + FastAPI
Structured database
SQLite
Knowledge store
Obsidian-compatible local Markdown vault
Search
Local text search + local embeddings/vector retrieval
Local LLM
Ollama-compatible provider
Cloud AI
Provider abstraction for OpenAI / Anthropic / future services
• 
• 
• 
• 
50


---

## PDF Page 51

Graph/Core
Three.js + React Three Fiber or suitable custom WebGL implementation
Motion
Motion for React / targeted custom animation
UI components
Custom Ion system, with selective use of mature component libraries rather than allowing a library to
determine Ion's visual identity
Google
Google Calendar/Gmail APIs
School
Canvas API
Development
GitHub API
Secrets
macOS Keychain
82. Design System Package
Create reusable internal design primitives rather than scattering visual constants across files.
Possible package:
packages/ion-design/
Contains:
color tokens;
typography;
spacing;
buttons;
overlays;
• 
• 
• 
• 
• 
51


---

## PDF Page 52

progress components;
transitions;
icons;
interaction patterns.
The design language may later influence the user's portfolio and visual projects without requiring them to
be identical.
83. Public Repository Safety
The public Ion repository must never contain real personal Ion data.
Ship synthetic fixtures such as:
Demo Course
Demo Assignment
Demo Internship
Demo Project
Demo Calendar
Screenshots/demos intended for recruiters should use synthetic data.
User database and vault remain outside the repository.
84. Development Repository Structure
Recommended conceptual structure:
ion-os/
├── README.md
├── AGENTS.md
├── CHANGELOG.md
│
├── docs/
│   ├── PRODUCT_SPEC.md
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── SECURITY.md
│   ├── AI_SYSTEM.md
│   ├── DESIGN_SYSTEM.md
│   ├── INTEGRATIONS.md
• 
• 
• 
• 
52


---

## PDF Page 53

│   └── DECISIONS.md
│
├── apps/
│   ├── desktop/
│   └── api/
│
├── packages/
│   ├── ion-design/
│   ├── shared-types/
│   └── ai-router/
│
├── fixtures/
│   └── synthetic/
│
└── tests/
Exact structure may change once the stack is scaffolded.
85. Coding-Agent Development Rules
Codex/Claude Code are development tools, not Ion's runtime.
To conserve usage:
Product decisions happen before coding.
Work occurs in small milestones.
Begin agent work from a clean Git state.
Create meaningful commits.
Ask the agent for a plan before major edits.
Restrict file scope when possible.
Review diffs.
Run the application.
Run relevant tests.
Add tests for important behavior .
Document architectural changes.
Do not allow coding agents to casually redesign architecture.
Never let an agent execute destructive commands without understanding them.
Prefer readable code over clever code.
Useful coding-agent instruction pattern:
Read the relevant specification files first. Implement only milestone X. Explain your plan
before editing. Do not modify unrelated modules. Add/update tests. Run the relevant test
1. 
2. 
3. 
4. 
5. 
6. 
7. 
8. 
9. 
10. 
11. 
12. 
13. 
14. 
53


---

## PDF Page 54

suite. At completion, summarize changed files, architectural decisions, and manual
verification steps.
86. Comments and Maintainability
Code comments should explain:
non-obvious reasoning;
safety invariants;
tricky scheduling logic;
integration assumptions;
AI permission boundaries;
unusual performance decisions.
Do not clutter the codebase with comments explaining obvious syntax.
Documentation should allow the user to ask another LLM:
Explain how Ion's calendar synchronization works.
without the LLM needing to reverse-engineer the entire repository.
87. Initial Personal Baseline
The user's real current state is explicitly excluded from this master specification.
After the base system is defined, create a private onboarding dataset containing:
current areas;
current courses;
current tasks;
active projects;
active goals;
milestones;
current applications;
research goals;
graduate-school aspirations;
routines;
finances the user chooses to track;
current library information.
Baseline records should contain dates and statuses so Ion naturally reduces their influence as
circumstances change.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
54


---

## PDF Page 55

This data must never appear in the public Git repository.
88. Development Phases
Phase 0 — Repository + Engineering Foundation
Build:
Git repository;
docs;
architecture records;
linting/formatting;
testing;
Tauri/React shell;
Python service;
SQLite connection;
logging;
settings;
synthetic fixtures.
No AI.
No Google.
No Canvas.
Goal:
A stable, understandable foundation.
Phase 1 — Ion Core Personal Organizer
Build:
Home shell;
Today;
tasks;
areas;
goals;
milestones;
projects;
local database;
basic command search;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
55


---

## PDF Page 56

audit log;
trash/undo;
basic menu-bar application.
Still mostly deterministic.
Goal:
Ion already works as a useful local planner without integrations or AI.
Phase 2 — Calendar
Build:
Google OAuth;
multiple calendars;
two-way sync;
locked/flexible/Ion event states;
tasks vs work blocks;
drag/drop;
conflict detection;
schedule suggestions.
Goal:
Ion becomes the primary calendar planning interface.
Phase 3 — Canvas + School
Build:
Canvas integration;
assignments;
syllabi;
deadlines;
grades;
submission verification;
studying;
course dashboard;
understanding model.
Goal:
Most academic responsibilities enter Ion automatically.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
56


---

## PDF Page 57

Phase 4 — Local AI
Add:
provider interface;
Ollama;
structured output validation;
task extraction;
assignment decomposition;
capture classification;
daily-review parsing;
safe link suggestions.
Goal:
AI removes organizational work without becoming necessary for core functionality.
Phase 5 — Gmail
Build:
multiple-account support;
metadata triage;
selective-body processing;
email-to-task;
deadline/change detection;
cleanup system;
draft creation.
Goal:
Ion begins proactively understanding external obligations.
Phase 6 — Weekly Planning + Focus Intelligence
Build:
Sunday reset;
duration models;
time estimation;
focus sessions;
minimum viable progress;
overload detection;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
57


---

## PDF Page 58

rescheduling;
longitudinal insights.
Goal:
Ion starts adapting planning to actual behavior.
Phase 7 — Knowledge + Obsidian
Build:
vault management;
Raw Inbox;
capture;
companion notes;
semantic search;
structural/contextual/soft relationships;
Knowledge Gap system;
decision memory.
Goal:
Ion becomes a genuine second brain.
Phase 8 — Career + Research + GitHub
Build:
opportunity discovery;
internship/job tracking;
application pipeline;
research model;
resume versions;
GitHub integration;
portfolio-readiness analysis.
Goal:
Ion actively helps build professional readiness.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
58


---

## PDF Page 59

Phase 9 — Graduate School
Build:
program discovery;
program profiles;
research/lab alignment;
preparation evidence;
readiness analysis;
application planning;
longitudinal progress assessment.
Goal:
Ion helps shape actions toward competitive graduate-school preparation.
Phase 10 — Finance
Build:
spreadsheet/CSV import;
transactions;
categories;
budgets;
savings;
financial projections;
purchases/scenarios;
investments/taxes/credit tracking;
strong Private Local boundaries.
Goal:
Useful personal finance analysis without banking credentials.
Phase 11 — Library
Build:
Books;
Movies;
TV;
Games;
spreadsheet imports;
metadata;
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
59


---

## PDF Page 60

ratings/progress;
recommendations;
soft knowledge relationships.
Phase 12 — Cloud Deep Ask
Build:
OpenAI/Anthropic provider(s);
model router;
context minimization;
cloud privacy boundary;
usage ledger;
user budget;
Fast/Deep/Max modes.
Goal:
Frontier reasoning available selectively at controlled cost.
Cloud Deep Ask may be moved earlier if project development or graduate-school analysis proves valuable
enough.
Phase 13 — Ion Core Visualization
The visual sphere can be prototyped earlier , but the advanced data-connected version belongs here.
Build:
dense sphere;
state animation;
WebGL performance controls;
graph density;
360° interaction;
zoom;
scope-in;
cluster labels;
data relationships.
Goal:
Turn the existing data model into Ion's defining visual interface.
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
60


---

## PDF Page 61

Phase 14 — Mobile Companion
Build:
Today;
Tasks;
Calendar;
Capture;
Focus;
Ask Ion;
reviews;
caching;
synchronization;
notifications.
89. Definition of Success
Ion succeeds when the user can begin a normal week without manually reconstructing their life.
A mature weekly workflow should approximate:
Sunday
Ion already knows:
• assignments
• deadlines
• calendar
• work/classes
• unfinished tasks
• important email
• applications
• projects
• goals
Ion generates:
• workload assessment
• proposed schedule
• conflicts
• recommended tradeoffs
User:
• reviews
• adjusts
• approves
• 
• 
• 
• 
• 
• 
• 
• 
• 
• 
61


---

## PDF Page 62

Ion:
• updates Google Calendar
During the week:
Ion monitors changes
→ surfaces important changes
→ records completion
→ learns duration patterns
→ proposes corrections
At night:
User completes short review
→ Ion updates progress
→ tomorrow adapts
Over months:
Ion detects patterns
→ improves estimates
→ tracks skill development
→ connects work to goals
→ identifies gaps
→ helps steer projects/career/education
The user should spend progressively less time administering Ion as Ion becomes more useful.
That is the central product requirement.
62

---

## Owner-approved architecture amendment — 2026-08-30

This amendment is canonical product direction adopted after the preserved
source transcription above.

### Developer Agent Bridge

Ion may eventually generate compact, repository-aware handoffs/prompts and
explicitly launch or resume external development agents for registered
projects. The first companion should prioritize Claude Code while keeping its
evidence vocabulary extensible to Codex and future agents. Those tools remain
external: they own their
authentication, process lifecycle, sessions, and conversations. Ion must never
read, store, reuse, export, or impersonate their credentials, and the renderer
must never receive generic shell or process authority. Any future launch path
uses narrow Rust-owned commands restricted to allowlisted repositories and
agent executables and requires explicit user action.
Handoff/prompt generation also requires an explicit user action.

Progress observation should prefer bounded structured agent events,
deterministic Git state, test/build outcomes, commits/checkpoints, and concise
completion summaries. Full transcripts, hidden reasoning, IDE screen scraping,
continuous full-repository watching, and fabricated completion percentages are
not default product behavior. Human work time and agent execution time are
distinct measures. Developer telemetry is Private Local unless a later
security decision explicitly authorizes remote exposure.

The first capability is a lightweight bridge, not an embedded coding runtime,
general terminal, process supervisor, IDE mirror, transcript archive, or
autonomous multi-agent platform. It may be separately scoped before Phase 8
when useful for building Ion; full GitHub and project-development intelligence
continues to mature in Phase 8. No additional numbered roadmap phase is
created.

### Deep Ask and resource boundary

External coding-agent use is separate from Ion Deep Ask. Normal Claude Code
uses the user's Claude subscription and never receives Ion's Anthropic API
credential. Future Deep Ask credentials belong in macOS Keychain or equivalent
secure storage and remain subject to local retrieval, context minimization,
sensitive-data filtering, Private Local exclusions, deliberate cloud use, and
configurable usage/cost budgets.

Persistent intelligence does not require persistent computation. Baseline Ion
must remain useful without an always-loaded local model, continuous WebGL,
continuous repository indexing, unbounded caches/history, per-integration
polling workers, whole-database renderer mirrors, or embedded heavyweight
agent runtimes. Heavy systems initialize on demand, suspend when inactive, use
bounded projections, and release resources after meaningful idle periods.
Approximately 300 MB Ion-owned idle memory is an initial soft target; an idle
baseline approaching or exceeding approximately 500 MB requires investigation
unless measured requirements justify it. External agents, IDEs, and Ollama are
measured separately. Normal fluctuation is acceptable; memory must not grow
materially and monotonically merely because Ion remains open for days.

---

## Owner-approved product / roadmap amendment — 2026-08-31

This amendment is canonical product direction. It preserves the source
transcription above while superseding its Phase 14 roadmap entry. It authorizes
no implementation, schema, dependency, integration, or mobile-sync design.

### Tasks, CalendarBlocks, and completion evidence

Ion Task remains the canonical task system. Google Tasks and the previously
considered Phase 2D bridge are optional future integration work, owner-deferred
and not required for desktop v1. Tasks and Calendar events remain distinct
canonical records and distinct visual concepts.

A Task may have one or more scheduled Calendar work blocks without becoming an
event; completion of a work block does not by itself complete its related Task.
Future Today and Calendar surfaces may offer task completion where appropriate.
Future integrations may provide completion evidence: deterministic evidence may
update related canonical records under accepted authority, while uncertain
inference requires confirmation. Meaningful completion/progress may propagate
through related Milestones, Goals, readiness checkpoints, and Projects without
duplicating the canonical Task.

### Aspirations, readiness, and Skills

The future product model may situate current Goal semantics in:

```text
Area → Aspiration → Goal / readiness checkpoint → Milestone → Task
```

Areas are continuing domains of growth and are not permanently completed.
Aspirations express desired outcomes or directions. An Aspiration may have a
finite current set of readiness/preparation checkpoints that maximize
preparation for that outcome. Completing preparation checkpoints means a
preparation target was achieved; it must not claim that an external outcome is
guaranteed or achieved.

Skills are cross-cutting relationships, not a strict tree. Coursework,
projects, repositories, research, tasks, assessments, and other evidence may
contribute to multiple Skills and readiness checkpoints without duplicating
canonical records. Progression should remain evidence-backed and categorical
unless a numeric measure has real meaning; fabricated percentages, XP, and
false precision are prohibited. Future planning or AI may propose and revise
readiness plans from known context and evidence, but direct owner edits and
decisions outrank automation. User-specific aspirations and checkpoints remain
runtime data, never product configuration.

### Ion Core and knowledge relationship

The sparse Home Core is the early representation of the future production Ion
Core. Phase 13 evolves that same signature information/data lens into the
polished spatial spherical relationship graph; it does not create a competing
primary graph. Knowledge/Obsidian, Projects, Areas, Goals/Aspirations, Skills,
research, and other canonical relationships may contribute to the unified Core.
Obsidian may provide useful knowledge-specific views, but the signature Home
visualization remains Ion Core.

Core remains informational rather than decorative. Its restrained glow/pulse,
reduced-motion support, visibility throttling, background suspension, and
performance requirements remain binding.

### Phase 14 — Voice & Ambient Core

Phase 14 replaces Mobile Companion in the numbered desktop-v1 roadmap.

Build direction:

- Ask Ion may support optional voice input and optional spoken responses.
- Core states may communicate listening, processing, and responding.
- Microphone activation is explicit/push-to-talk or otherwise owner-triggered
  by default. Always-listening and wake-word behavior require a separate
  privacy/performance decision.
- Speech resources are local, lazy/on-demand, and released after inactivity
  where technically feasible. Voice respects local-first/privacy boundaries and
  exposes visible microphone state.
- Focus Mode may optionally enable music-reactive Core behavior from minimal,
  ephemeral playback/beat/energy signals. It does not store raw audio.
- Voice or music animation may affect pulse, glow, node displacement, or flow,
  but never canonical relationship-graph structure. It respects reduced motion,
  battery, memory, visibility, and `PERFORMANCE.md`.

Mobile Companion, cross-device sync, and remote access move to post-v1 future
platform expansion. Their synchronization, authentication, privacy, and
architecture decisions remain deferred.

### Deferred multi-calendar event mirroring

After the normal single-provider event lifecycle is complete, an Ion event may
eventually intentionally appear in multiple connected provider
calendars/accounts. The preferred conceptual model is one canonical Ion
CalendarBlock/event with multiple provider linkage/copy records, not duplicated
canonical events and not attendee invitations. Future design must address
partial provider failure, direct provider edits, deletion of one copy,
permission loss, conflict behavior, and idempotency. This is deferred Calendar
direction only and is not Phase 2C-3 scope.

## Owner-approved Calendar authority amendment — 2026-09-01

This amendment is canonical product direction, adopted after real owner
acceptance testing of the Phase 2C Calendar. It preserves the source
transcription above while superseding the passages named below. It authorizes
no implementation, schema, dependency, or integration change by itself.

It supersedes:

- §11's flexibility rule, "Ion may not modify locked events without explicit
  confirmation," **as applied to direct human action**;
- §61's "Provide Retry" as the expected shape of ordinary Calendar write
  recovery;
- any reading of §62 that treats ordinary provider version drift as a
  conflict the user must resolve.

### Direct human action is authorization

When the owner directly edits, drags, resizes, or deletes an event, or chooses
a recurrence scope, **that action is the authorization.** Ion carries it out.

Ion does not ask for an additional confirmation merely because an event is
marked locked, because the change reaches a provider, or because the write is
consequential. Confirmation is reserved for actions Ion cannot truthfully
offer to reverse — principally destructive recurrence operations.

For ordinary reversible actions Ion prefers **action → immediate result →
Undo** over **action → confirmation → apply → sync**. A confirmation asks the
owner to predict a mistake; an Undo lets them correct one. Calendar Undo stays
bounded and provider-safe, and this establishes no general application-wide
undo or event-sourcing requirement.

### `flexibility` governs automation, not the owner

`locked` / `flexible` / `Ion-controlled` remain meaningful planning metadata.
Their purpose is to constrain **Ion's own scheduling and future AI**: the
Scheduling Engine (§16) may freely place and move `flexible` time, and must
not move a `locked` commitment without the owner's approval, exactly as §16
already requires consequential proposed changes to be reviewed.

That constraint governs Ion acting on its own. It is **not** a permission
boundary between the owner and their own calendar. Every event synced from a
provider is `locked` by default, so treating it as a human-edit gate put a
confirmation in front of essentially every real edit — friction that taught
nothing and protected nothing.

> **Human direct action → already authorized.**
> **Ion automation / autonomous rescheduling → governed by permission and
> approval policy.**

Safety language elsewhere in this specification about approval, review, and
consequential automated action applies to the second, not the first.

### One authorization step, and only one

Ion has exactly two authorization models, and every Calendar action falls under
one of them.

| Origin | Authorization |
| --- | --- |
| The owner acting directly | the action itself |
| Ion's scheduler, or AI/LLM proposing a change | the owner accepting the proposal |

**Automation proposes; the owner approves; approval happens once.** An AI or
scheduler-originated Calendar change is a candidate until the owner accepts it —
"Move study block from 5 PM to 7 PM?" → **Apply**. That Apply *is* the
authorization, and it is the last one.

> After an authorization — human-direct or owner-approved — **nothing may ask
> again.** Persisting, dispatching to the provider, reconciling a provider
> version, and settling are consequences of the decision already made, not
> further decisions. Provider synchronization is never a second approval step.

This does not grant automation any standing permission. Autonomous Calendar
mutation without owner approval is not authorized today; if Ion later offers
owner-configurable automation permissions for specific categories, that is a
separate product decision to be recorded explicitly, not inferred from this
section. §16's requirement that the owner review consequential proposed changes
is the automation half of this rule, unchanged.

### Ion ↔ Google convergence is automatic

§11's "true two-way synchronization" is a product requirement about behavior,
not merely about capability:

- a supported direct-human change in Ion propagates to Google automatically;
- a supported change made in Google propagates back into Ion automatically.

Manual synchronization is a refresh and troubleshooting affordance. It is
never a step in a successful Calendar workflow, and neither are provider
retry, apply, or reconciliation controls. Ion's outbox, provider versions, and
write states are implementation detail and must not surface as user workflow.

### Semantic conflict is not sync concurrency

§62 is correct about **semantic conflict** — genuinely contradictory facts Ion
cannot deterministically resolve, such as a syllabus saying Thursday while
Canvas says Friday. Ion should surface that uncertainty and let the owner
decide, because guessing would be dishonest.

**Sync concurrency is a different thing and must not be presented as a
conflict.** A provider version changing while an Ion edit was in flight is an
ordinary distributed-systems event, not a disagreement about a fact. Where Ion
can deterministically preserve the fields the human changed while adopting the
provider's latest values for fields they did not touch, it reconciles
automatically and says nothing.

While a direct-human write is unsettled, Ion owns **only the provider fields
that human explicitly changed**; the provider's latest state owns every other
provider field; Ion-only metadata stays Ion's; and the pending human values
stay visible until the write settles. Once it settles, that temporary
ownership ends and later provider changes synchronize back normally. This is
deliberately not timestamp last-write-wins.

### What still deserves the owner's attention

Genuinely exceptional conditions remain explicit, with recovery specific to
the condition rather than a generic chooser: the provider event was deleted
while an edit was pending, write permission was downgraded, reauthentication
is required, a recurrence identity no longer resolves, the event became an
unsupported provider structure, the provider rejected the change terminally,
or bounded automatic recovery was exhausted. The goal is no routine conflict
management — not concealing real contradictions.

### Behavioral parity and where the detail lives

Unless an Ion override is explicitly recorded, ordinary Calendar interaction
mechanics follow familiar Google Calendar desktop behavior as closely as Ion's
accepted architecture and security model safely allow. Ion keeps its own
visual identity, local-first architecture, and trust boundary; parity is about
interaction semantics, never branding or provider architecture.

**[Calendar interaction behavior](CALENDAR_BEHAVIOR.md) is the detailed
Calendar interaction contract** and the authority for how these principles are
applied — drag and resize, save behavior, recurrence scope timing and its
modal, confirmation, Undo, automatic convergence, and error treatment. This
specification states the product philosophy and authority model; that document
states the mechanics. Where this specification's preserved transcription and
that contract disagree about Calendar interaction detail, the contract governs.

## Owner-approved roadmap amendment — 2026-09-02

This amendment is canonical product direction. It preserves the source
transcription above, and supersedes the Phase 14 designation made by the
2026-08-31 amendment. It authorizes no implementation, schema, dependency, or
integration change by itself.

It supersedes:

- the 2026-08-31 amendment's **Phase 14 — Voice & Ambient Core** designation;
- and, for the avoidance of doubt, the preserved transcription's
  **Phase 14 — Mobile Companion**, which the 2026-08-31 amendment had already
  displaced. Both remain in this document as history and are not rewritten.

### Active numbered roadmap

| Phase | Name |
| --- | --- |
| 13 | Ion Core Visualization (unchanged) |
| 14 | **Final UI/UX Overhaul & Visual Cohesion** |

**Mobile Companion is post-v1.** It is outside the active numbered v1
implementation roadmap, requires its own architecture and security
authorization, and must not begin automatically as Phase 14.

**Voice & Ambient Core** is displaced from Phase 14. Its accepted build
direction in the 2026-08-31 amendment stands unchanged as product direction; its
position in the numbered roadmap is an open owner decision and it is not
scheduled by this amendment.

### The deferral principle

During Phases 2 through 13, every surface must still be functional, usable,
accessible, responsive, and conformant to the established design system. What is
deferred is **holistic cross-product visual redesign and accumulated cosmetic
polish** — unless an issue materially harms usability, in which case it is fixed
in the phase that owns the surface.

This exists so that earlier phases are not repeatedly reopened for cosmetic
reasons, and so that cohesion work happens once, across the whole product, with
the real surfaces in front of the owner.

### Phase 14 scope

Final desktop-wide visual cohesion:

- navigation and information hierarchy
- typography and spacing
- control and component geometry and consistency
- visual density
- cross-surface cohesion
- responsive and window-size polish
- motion and transitions where appropriate
- design-token and component cleanup
- accumulated holistic polish deliberately deferred from earlier phases

**Phase 14 does not invent missing functionality.** Earlier functional phases
remain responsible for the capabilities they own; Phase 14 makes what exists
cohere. Where it finds a genuine functional gap, that gap belongs to its owning
phase, not to Phase 14.

The design authority for this work remains
[Design system](DESIGN_SYSTEM.md), and for Calendar surfaces
[Calendar interaction behavior](CALENDAR_BEHAVIOR.md).
