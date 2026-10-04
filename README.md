# Career OS

A local, open-source job-hunting system that runs on your own laptop. It **finds** jobs, internships, fellowships and scholarships around the world. It **autofills** the applications and then stops, so you review each one and click Submit yourself. It **tracks** replies from your Gmail and drafts follow-ups. It **teaches** you for every target role, with an AI examiner.

- **No API bills, your choice of AI.** The agents run your AI's official command-line app, signed in with your own subscription: [Claude Code](https://claude.com/claude-code) (Claude Pro/Max), [OpenAI Codex CLI](https://github.com/openai/codex) (ChatGPT Plus/Pro) or [Gemini CLI](https://github.com/google-gemini/gemini-cli) (Google account). Career OS removes API-key variables (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`…) from the agents' environment, so it can never charge you API fees. Switch any time in Settings → Your AI.
- **Everything stays local.** SQLite database, your CV, your answers and your browser profile never leave your machine.
- **You stay in control.** Nothing is ever submitted for you. Sites that ban bots (LinkedIn, Indeed…) are never automated.

## Tabs
| Tab | What it does |
|---|---|
| **Apply** | Scouts read public job boards (Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Workday, Arbeitnow, Remotive, Himalayas, Jobicy, plus optional Adzuna/Reed keys) twice a day. Research agents (Claude + web search), one per field × country, find fellowships, scholarships, part-time work and roles at firms with no public API. Matches are scored, cover letters drafted, and forms autofilled: green = your answer, amber = Claude's draft, red = you fill it. Your edits are learned. |
| **Track** | A pipeline board (Submitted → Responded → Assessment → Interviewing → Offer / Closed), driven by your Gmail over IMAP with an app password. Applications you made elsewhere are added from their "thanks for applying" emails. Follow-up drafts go to Gmail Drafts after N quiet days. Windows pop-ups show deadlines. |
| **Learn** | Mandatory tracks: Maths, Probability & Statistics, CS Foundations, DSA, Software & Systems, Interview Skills. Role tracks: SWE, Quant Researcher/Trader/Developer, ML Engineer, Research Scientist, Data Scientist, Salesforce, Slack, Trading. Each has free resources, your own PDFs matched by filename, notes, a "Test me" examiner (MCQ, short answers, and Python coding problems run locally) and mock interviews. |
| **Agents** | Every scout and research agent is listed here. You can run, enable, schedule and delete them, see their live logs, add new ones, and check which company boards are working. |

## Works for anyone
The first time it opens, a 9-step setup wizard asks for:

1. **Your career folder and CV.** Pick one folder for everything about you (for example `D:\My career`). Your CV is saved there, along with anything else you want Claude to know: old CVs, cover letters, statements, transcripts, project write-ups.
2. **Connect your AI.** Pick Claude, ChatGPT or Gemini, install its app with one click and sign in with your subscription.
3. **Claude gets to know you.** Claude reads the folder and writes what it understood into `career-os/about-me.md` inside it (you can read and edit it). It then asks you questions about anything it couldn't tell.
4. **About you.**
5. **Education.** Your degree picks your core Learn tracks.
6. **Goals.** Any roles, including ones you type yourself, plus countries and kinds of opportunity.
7. **Right to work.** Where you need sponsorship.
8. **Files and Gmail.**
9. **Learning plan.**

Everything else is generated from those answers: the agent line-up, match scoring and the Learn plan. Roles that aren't in the catalog get a custom Learn track, built by Claude from free sources. You can change your answers any time in Settings → *Edit my profile & goals*.

## Extra: your own job platforms
Separate from the scouts and finders. On the **Extra** page you add any job platform you like (LinkedIn, TargetJobs, Gradcracker, a niche board). Your AI first checks that it's a real job site. You then sign in once, yourself, in Extra's own browser window, and Career OS never sees your password.

Twice a day, at times you choose, Extra searches your roles × places on each platform. It scrolls the results at a human pace and keeps each job's role, company and place. It never applies or messages anyone. It then looks for each job on the company's **own** careers page or job system and adds what it finds to Matches, marked "extra". Jobs it can't find on the company's own site can be shown too, so you can apply on the platform yourself. Sites like LinkedIn don't allow automated reading, even of your own signed-in view, so there is some risk to your account there. The defaults are slow and small.

## Status ring
The circle with your initials (bottom left) has a ring. It is green when everything works and amber when your AI plan's limit is reached. It turns red, with a pop-up, when your AI is signed out or missing, or when Career OS itself has stopped.

## How the autofill works: it reads first, then fills
1. It fills only the obvious fields straight away: your name, email, phone, links and CV upload. Fields about *someone else*, such as a referee's email, are never filled with your details.
2. Claude reads the whole page like a person would: the instructions ("also apply on our Constellation form"), length hints, links, and which boxes are consents. It also reads your `about-me.md` and the answers you gave on earlier forms.
3. It writes long answers in your voice and only from real facts (amber), with a note under each one. Anything only you can know, such as referees, salary or a "% likely to accept" figure, goes red with a note saying exactly what's needed.
4. If the page says the real application is somewhere else, it opens that form in a new tab and fills it for the same application.
5. Consents and declarations are listed for you to read. Nothing gets ticked until you press **Tick acknowledgements**.
6. Type your own rough answer and press **Polish my text**. Claude tidies it while keeping your meaning, and **Undo polish** brings your original back.
7. You click the site's Submit. Your final long answers are saved to `career-os/answers-history.md` in your folder, so future forms stay consistent.

## Learn: beginner to research level
Every track has 5 levels: **Foundations → Core → Advanced → Expert → Frontier**. Frontier covers current research: key arXiv papers and open problems.
- **Generate with Claude** fills a level that has no modules yet.
- **Refresh sources** looks for newer free material, checking each link.
- **Add any subject** builds a whole new track.
- **The AI teacher** explains step by step. It searches the web for current free sources and cites them. It can read the PDFs in your books folder, and it runs quizzes and mock interviews.

Only free, legally open resources are used: open textbooks, OCW courses, official docs and arXiv papers.

## Quick start (Windows)
1. Unzip anywhere, e.g. `C:\career-os`.
2. Double-click `start.bat`. On the first run it:
   - installs Python if it's missing,
   - creates a private venv,
   - installs the packages,
   - installs Claude Code if needed.
3. Once only: open a terminal, run `claude`, and sign in with your **Claude Pro or Max account**. Choose the subscription login, not an API key.
4. Finish the setup wizard. It opens by itself the first time.
5. Optional: run `install-autostart.ps1` so Career OS starts when you log in. The scouts only run while it's running.

Command line: `.venv\Scripts\python -m careeros help`. `CLAUDE.md` lets an interactive `claude` session in this folder act as the "commander".

## Honest limits
- Your Claude plan's usage limits cap how many Claude agents can run. Claude agents are the research agents, cover letters, the examiner and drafted answers. Settings → "Max Claude agents at once" controls this. Agents that hit the limit pause and retry later. Plain board scouts don't use Claude at all.
- Autofill works best on Greenhouse, Lever, Ashby and similar forms. Workday needs you to sign in, then press "Fill this page" on each step.
- Always read amber (Claude-drafted) answers before submitting.

## Privacy
`data/` and the personal files in `config/` are git-ignored: `profile.yaml`, `settings.yaml`, `career-facts.md` and `cv.md`. Books are served only to your own browser, from your own folder. They are never copied into the repo.

MIT licence.
