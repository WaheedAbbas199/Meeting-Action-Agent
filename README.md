# 🤖 Meeting Action Agent

**Turn Meeting Conversations into Clear, Actionable Tasks with AI**

Meeting Action Agent is an AI-powered application designed to help teams convert meeting conversations into structured summaries, action items, task owners, and deadlines.

The goal is to reduce manual follow-up work and help teams keep track of decisions and responsibilities after meetings.

## ✨ Key Features

- **Meeting Summarization** — Generate concise summaries from meeting content.
- **Action Item Extraction** — Identify tasks and follow-up actions from conversations.
- **Task Organization** — Structure extracted actions into readable, actionable items.
- **AI Integration** — Use an AI model to process meeting content.
- **Google Integration** — Support Google account integration where configured.
- **Environment-Based Configuration** — Keep credentials and application settings outside the source code.

> Feature availability depends on the current project implementation and configured integrations.

## 🎯 Problem Statement

Important decisions and responsibilities can get lost after meetings. Manually reviewing notes and creating follow-up tasks takes time and can lead to missed actions.

Meeting Action Agent aims to simplify this workflow by transforming meeting content into structured information that people can review and act on.

## 🏗️ Workflow

1. Provide meeting content to the application.
2. Process the content using the configured AI workflow.
3. Generate a meeting summary and identify potential action items.
4. Organize the results for review.
5. Use the extracted tasks for follow-up, with human review where appropriate.

## 🛠️ Technology Stack

Update this list to match the technologies actually used in your repository.

- **Language:** Python
- **AI / LLM:** Configured language model provider
- **Integrations:** Google OAuth / APIs, if configured
- **Configuration:** Environment variables
- **Version Control:** Git and GitHub

## 📂 Project Structure

Example structure — adjust it to match your actual files.

```text
meeting-action-agent/
├── app/
│   ├── main.py
│   ├── services/
│   └── ...
├── tests/
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── ...
```

## ⚙️ Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/meeting-action-agent.git
cd meeting-action-agent
```

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Create a local `.env` file using the project's example:

```powershell
Copy-Item .env.example .env
```

Add the required configuration values according to the application's setup instructions.

**Never commit `.env` files, API keys, OAuth client secrets, or access tokens.**

### 5. Run the application

Use the actual startup command documented in the project. For example, if the application exposes a FastAPI instance at `app.main:app`:

```bash
python -m uvicorn app.main:app --reload
```

Open the local URL shown in the terminal.

## 🔐 Security Notes

- Store secrets in environment variables.
- Keep OAuth credentials and tokens out of version control.
- Request only the Google permissions required by the application.
- Review AI-generated summaries and action items before taking important actions.
- Avoid uploading confidential meeting recordings or personal information to unapproved services.

## 🧪 Testing

Run the project's available tests using the documented test command. If it uses pytest:

```bash
python -m pytest
```

Test results and supported functionality should be documented as they are verified.

## 🚀 Future Improvements

Potential enhancements include:

- Calendar and meeting-platform integrations
- Improved task assignment and deadline detection
- Editable action items and human approval workflows
- Export to task management platforms
- Meeting history and searchable summaries
- Authentication, role-based access control, and audit logs
- Production deployment, monitoring, and automated testing

These are planned enhancements, not claims of existing functionality.

## 👨‍💻 Author

**Waheed Abbas**

Computer Science graduate focused on AI/ML, Agentic AI, and practical AI engineering solutions.

- **GitHub:** [WaheedAbbas199](https://github.com/WaheedAbbas199)
- **Portfolio:** [View Portfolio](https://waheedportfolio-blush.vercel.app/)

## 📄 License

Add a license if you intend to distribute this project publicly. Until a license is added, do not assume others have permission to reuse the code.

---

*Built as a practical AI engineering project exploring how meeting conversations can become structured, actionable workflows.*