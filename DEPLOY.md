# Deploying and running the report

This guide is for whoever takes over the South Boise Village development report. The repository already contains everything: code, current data, redacted drawings and the daily workflow. Deploying it means turning on GitHub Pages and confirming the daily workflow runs.

**Live page:** https://hydrotylerking.github.io/sbv-development/
**Repository:** https://github.com/HydroTylerKing/sbv-development

---

## 1. Get access

- Ask the repository owner to add you under **Settings → Collaborators** with write access, or to transfer the repository to you (**Settings → General → Danger Zone → Transfer ownership**).
- Click **Watch → Custom → Issues** on the repository so you get an email when the daily check opens an issue.

## 2. One-time setup

Do these once, as someone with admin rights on the repository.

1. **Turn on GitHub Pages.** Go to **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
2. **Let the workflow save its results.** Go to **Settings → Actions → General → Workflow permissions** and choose **Read and write permissions**. The workflow commits each day's results back to `data/` and opens issues.
3. **Run it once.** Go to **Actions → Daily city check → Run workflow**, leave "Check the City of Boise for changes" ticked, and click **Run workflow**. It takes 5 to 10 minutes.
   - When it finishes, the page is live at the address above. The run's summary shows the link under **deploy**.
   - Open **Actions → the run → build → "Check the city and rebuild the page"** to read the changes report. If permits.cityofboise.org refuses GitHub's servers, you'll see repeated timeouts or 403 errors there. See Troubleshooting.

The workflow then runs on its own every morning at 6:55 am Mountain Daylight Time (5:55 am in winter). GitHub may start scheduled runs up to an hour late.

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
| Every morning the workflow checks the city, redraws the map, republishes the page and saves `data/changes/<date>.txt` | Nothing |
| The city posted something that needs attention, such as a new project, status change, new document, appeal, notice map or hearing | The workflow opens an issue titled "City changes to review: <date>". Follow [EDITING_GUIDE.md](EDITING_GUIDE.md): read the city documents, edit `data/projects.json`, commit to `main`, then close the issue |
| You commit to `main` | The workflow rebuilds and republishes the page within a few minutes. It doesn't re-check the city |
| You want a check right now | **Actions → Daily city check → Run workflow** |

Small text edits to `data/projects.json` can be made in GitHub's web editor: open the file and click the pencil icon. The workflow rebuilds the page after you commit. If the JSON has a mistake, the build fails and GitHub emails you. Fix it and commit again.

Adding drawings or notice areas needs your own computer (next section). The redaction step must be checked by eye before anything is published.

## 5. Working on your own computer

Needed for adding drawings and notice areas, and useful for previewing edits.

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

**Adding a drawing**, in short (full rules in EDITING_GUIDE.md):
```
python aca.py CZC26-00227 downloads --match "ELEV"
python redact.py "downloads/<file>.pdf" 1 images/name_elev.jpg --record CZC26-00227 --retrieved 2026-10-30 --terms "Owner Name" --preview check.png
```
- Open `check.png` and confirm that no private names, phone numbers, emails or home addresses remain. If OCR missed something, add `--box x0,y0,x1,y1` (fractions of the page) and run again.
- Then add the image and its `source` to the project in `data/projects.json`.
- Never commit downloaded PDFs. `.gitignore` already excludes them.

**Adding a notice area** when a case gets a "NOTICING RADIUS MAP":
```
python sbvmap.py notice "downloads/<radius map>.pdf" "1911 S MANITOU AVE"
```
Put the printed addresses in the project's `notice.addresses`, then commit. The workflow redraws the map on its next city check.

## 6. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| The run fails at "Check the city" with timeouts, 403 or 503 from permits.cityofboise.org | The city's site may be slow or down; re-run later. If it fails every day, the city may be blocking GitHub's servers. Run `python update.py` on your own computer, then commit and push `data/`. The page republishes from your push |
| The run fails at "Rebuild" or "Rebuild only" | Usually invalid JSON in `data/projects.json`. The log names the line. Fix it and commit |
| The run fails at "Save the day's results" | Workflow permissions aren't set to read and write (step 2.2), or someone pushed during the run. Re-run |
| Pages deploy fails with "Pages not enabled" | Step 2.1 |
| No runs for a while | GitHub pauses scheduled workflows after 60 days with no repository activity. The daily commits normally prevent that. To restart, go to **Actions → Daily city check → Enable workflow** |
| An issue lists a project as "NOT ON TRACKER" | Expected for approved projects: the city's tracker drops them once approved. The issue only opens when there are other changes |
| The first run reports nothing | The first run on a fresh checkout records a starting point; later runs report changes against it. This repository already has one, from Oct 25, 2026 |

To stop the daily check, go to **Actions → Daily city check → ⋯ → Disable workflow**. The published page stays up.

## 7. Content rules

[EDITING_GUIDE.md](EDITING_GUIDE.md) has the full rules. The three that matter most:
- **Facts from city documents only.** Write "Not shown" rather than guess.
- **No private information.** Never publish a private person's name, phone, email or home address, including owners, appellants and neighbors on plats. Firms, design professionals and city staff named in city notices are fine.
- **Neutral wording.** Say what was requested, decided or scheduled, and when. No opinions.

## 8. History

Until October 2026 the report was produced and checked daily by scheduled Claude tasks and hosted on claude.ai. This repository replaces that setup and is now the only copy in charge.
