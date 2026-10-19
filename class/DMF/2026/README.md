# Digital Media & Flourishing — course site

Open `index.html` in a browser to view it locally. Online it lives at
https://umipo.github.io/class/DMF/2026/ — an unlisted page of the umipo.github.io site
(not linked from the site, kept out of the sitemap, marked noindex).

Pages: the syllabus (home), Student work (`#work`, behind a passcode), and one page per
student (`#student-name`). The passcode lives in `passcode.txt` (not committed to git); only its SHA-256 hash is
written into the page. Change it there and rebuild to rotate it. Course text and the schedule live in `course.json`;
the "Next" marker on the schedule is computed from today's date when the page opens.

## Adding students

1. Put each student's files in their own folder inside `Personal Brands/` on the Mac (the path
   is set in `local.json`, which stays out of git), named after the student (e.g. `Pema Choden/`). The build recognises files by name:
   - business card → filename contains `card` (PDF with 2 pages, or `front`/`back` PNGs)
   - carousel      → filename contains `carousel`, `instagram` or `slides`
                     (one PDF page per slide, or one tall page with all slides stacked)
   - logo (optional) → filename contains `logo` or `mark` (PNG/JPG/PDF). Shown centred on
                     the brand colour in the gallery; without it the guide cover is used.
   - brand guide   → any other PDF
2. Optionally add a `brand.json` to the folder (copy one from an existing student) with
   the brand title, role, tagline, descriptor words, carousel title, credit line and links.
   Without it the site shows the folder name and "Designed by <name>".
3. In Terminal:

       cd ~/Desktop/Teaching\ Materials/DMF/umipo.github.io/class/DMF/2026
       python3 build.py
       cd ~/Desktop/Teaching\ Materials/DMF/daumkim.com
       git add -A && git commit -m "Update course site" && git push

   This renders the PDFs to `assets/<student>/` and rewrites `index.html`.
   Rerun it any time a student replaces a file.

Course text (title, description, outcomes, schedule, notes) lives in `course.json`.

`build.py` needs `pdftoppm` (poppler), Pillow and numpy — all present on this Mac.
