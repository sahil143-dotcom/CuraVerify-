# Deploy CuraVerify (Hugging Face Spaces)

This project ships as a **Streamlit** demo. Hugging Face Spaces is the recommended host for NLP course demos (long-running Python + WebSockets). Vercel cannot run Streamlit.

## What the Space needs

| File | Role |
|---|---|
| `app.py` (repo root) | Space entrypoint |
| `requirements.txt` (repo root) | Lean demo dependencies |
| `scientific/app.py` | Product UI + verifier |
| `scientific/data/demo_samples.json` | Bundled REAL / HALL samples (no SQLite) |
| `scientific/results/eval_*.json` | Eval tab metrics |

Large BioLaySumm JSONL and `scientific.db` are **not** required on the Space.

## One-time: create the Space

1. Create a free account at [huggingface.co](https://huggingface.co/join).
2. **New Space** → SDK: **Streamlit** → hardware: **CPU basic**.
3. Either:
   - **Link this GitHub repo** as the Space source, with `app_file: app.py`, or
   - Push this repo to the Space git remote (see below).

Space README YAML (already at the top of the root `README.md`):

```yaml
sdk: streamlit
app_file: app.py
```

## Push from this machine

```bash
# install CLI once
py -m pip install huggingface_hub

# login (opens browser / asks for token with write access)
huggingface-cli login

# create Space if it does not exist (replace USER)
huggingface-cli repo create CuraVerify --type space --space_sdk streamlit -y

# add remote + push main
git remote add hf https://huggingface.co/spaces/USER/CuraVerify
git push hf main
```

Public URL shape: `https://huggingface.co/spaces/USER/CuraVerify`

## Local check (same code path as Space)

```bash
py -m pip install -r requirements.txt
streamlit run app.py
```

## After deploy

1. Open the Space URL → pick a **[HALL]** sample → **Run verification**.
2. Confirm E1–E4 grades and document verdict appear.
3. Put the URL into the root README **Live Demo** badge.
