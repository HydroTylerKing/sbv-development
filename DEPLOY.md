# Deploying and running the report

This guide is for whoever takes over the South Boise Village development report. The repository already contains everything: code, current data, drawings and the daily workflow. Deploying it means turning on GitHub Pages and confirming the daily workflow runs. After that the report updates itself every morning; **nobody needs to check or approve anything.**

**Live page:** https://hydrotylerking.github.io/sbv-development/
**Repository:** https://github.com/HydroTylerKing/sbv-development

---

## 1. Get access

- Ask the repository owner to add you under **Settings → Collaborators** with write access, or to transfer the repository to you (**Settings → General → Danger Zone → Transfer ownership**).
- GitHub emails the repository owner automatically if a daily run ever fails. That is the only notice you'll get.

## 2. One-time setup

Do these once, as someone with admin rights on the repository.

1. **Turn on GitHub Pages.** Go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
2. **Let the workflow save its results.** Go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions**. The workflow commits each day's results back to `data/` and `images/`.
3. **Run it once.** Go to **Actions → Daily city check → Run workflow**, leave "Check the City of Boise for changes" ticked, and click **Run workflow**. It takes 5 to 10 minutes.
   - When it finishes, the page is live at the address above. The run's summary shows the link under **deploy**.
   - Open **Actions → the run → build → "Check the city and rebuild the page"** to read the changes report. If permits.cityofboise.org refuses GitHub's servers, you'll see repeated timeouts or 403 errors there. See Troubleshooting.

The workflow then runs on its own every morning, scheduled for 5:55 am Mountain Standard Time (6:55 am in summer). GitHub starts scheduled runs on a best-effort basis and can delay them by hours, so hourly backup attempts follow until late afternoon; each stops within seconds once the day's check has run. Expect the page to update sometime between early morning and mid-afternoon.

You must be **signed in to GitHub** with write access to see the **Run workflow** button. You can also start a full city check by committing anything to `main` with `[check city]` in the commit message.

## 3. Put it on a website

The page is one self-contained file, with the images and map built in. Choose one way to show it:

- **Link to it** from your site: `https://hydrotylerking.github.io/sbv-development/`
- **Embed it** in a page:
  ```html
  <iframe src="https://hydrotylerking.github.io/sbv-development/"
          title="South Boise Village development"
          style="width:100%; height:90vh; border:0;" loading="lazy"></iframe>
  ```
- **Use your own address**, for example `development.sbvna.com`:
  1. In **Settings → Pages → Custom domain**, enter the address and save.
  2. At your DNS provider, add a CNAME record from `development` to `hydrotylerking.github.io`.
  3. When the check passes, tick **Enforce HTTPS**.

The page always shows the latest published version. Nothing on the website needs to change when the report updates.

## 4. Day-to-day

| What happens | What you do |
|---|---|
| Every morning the workflow checks the city, applies the changes by rule, redraws the map, republishes the page and saves `data/changes/<date>.txt` | Nothing |
| A new project, approval, appeal, hearing date, new drawings or a notice map appears on the city's records | Nothing: it is added to the page automatically and listed under "Recent changes" |
| You want to add detail or fix a wording (optional) | Edit `data/projects.json` in GitHub's web editor (pencil icon) and commit. The page republishes within minutes. See [EDITING_GUIDE.md](EDITING_GUIDE.md) |
| You want a check right now | **Actions → Daily city check → Run workflow** |
| A run fails | GitHub emails the owner. Usually the city's site was down; the next day's run catches up. See Troubleshooting |

Automatic text is factual but plain: new projects show what the city publishes and "Not shown" for anything it doesn't. Hand edits are kept until the city posts something new about that project.

Phone numbers and emails on drawings are blacked out automatically. To show drawings exactly as filed, set `SBV_REDACT_CONTACTS: "false"` in `.github/workflows/daily.yml`.

## 5. Working on your own computer (optional)

Only needed to preview edits or run an update by hand.

1. Install Python 3.10+ and git, then:
   ```
   git clone https://github.com/HydroTylerKing/sbv-development.git
   cd sbv-development
   pip install -r requirements.txt
   ```
2. Install the tools for drawings:
   - macOS: `brew install poppler tesseract`
   - Windows: poppler (github.com/oschwartz10612/poppler-windows) and tesseract (github.com/UB-Mannheim/tesseract/wiki), both added to PATH
   - Linux: `sudo apt install poppler-utils tesseract-ocr`
3. Preview: run `python update.py --build` and open `sbv_report.html` in a browser.
4. Always `git pull` before editing, because the workflow commits every day. Then commit and `git push`.
5. `python update.py` runs the same full update as the workflow (about 7 minutes).

## 6. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The run fails at "Check the city" with timeouts, 403 or 503 from permits.cityofboise.org | The city's site may be slow or down; the next day's run catches up. If it fails every day, the city may be blocking GitHub's servers. Run `python update.py` on your own computer, then commit and push `data/` and `images/`. The page republishes from your push |
| A notice map wasn't read ("notice map ... not read automatically" in the run log) | Some city maps have text that can't be read by machine. The project simply shows no notice area. Optional fix: enter the shaded addresses by hand (EDITING_GUIDE.md) |
| The run fails at "Rebuild" or "Rebuild only" | Usually invalid JSON in `data/projects.json`. The log names the line. Fix it and commit |
| The run fails at "Save the day's results" | Workflow permissions aren't set to read and write (step 2.2), or someone pushed during the run. Re-run |
| Pages deploy fails with "Pages not enabled" | Step 2.1 |
| No runs for a while | GitHub pauses scheduled workflows after 60 days with no repository activity. The daily commits normally prevent that. To restart, go to **Actions → Daily city check → Enable workflow** |
| A project shows as "NOT ON TRACKER" in the changes report | Expected for approved projects: the city's tracker drops them once approved. They retire on their own 30 days after the appeal period |
| The first run reports nothing | The first run on a fresh checkout records a starting point; later runs report changes against it. This repository already has one, from Oct 25, 2026 |

To stop the daily check, go to **Actions → Daily city check → ⋯ → Disable workflow**. The published page stays up.

## 7. Content rules

The automatic rules follow these, and hand edits should too:
- **Facts from city documents only.** Write "Not shown" rather than guess.
- **Neutral wording.** Say what was requested, decided or scheduled, and when. No opinions.
- **Contact details:** phone numbers and emails on drawings are blacked out automatically. Names appear as they do in the city's public files.

## 8. History

Until October 2026 the report was produced daily by scheduled Claude tasks and hosted on claude.ai. This repository replaces that setup with fixed rules that run on GitHub and is now the only copy in charge.
