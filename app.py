from flask import Flask, render_template, request, send_file
from lxml import etree
from io import BytesIO
import datetime

app = Flask(__name__)

def is_subsequence(codes, subsequence):
    if not subsequence:
        return False
    i = 0
    for code in codes:
        if code == subsequence[i]:
            i += 1
            if i == len(subsequence):
                return True
    return False

def parse_meos_controls(text):
    return [code.strip() for code in text.split(';') if code.strip()]

def extract_results_from_splits(runners, courses, lap_control):
    results = {name: [] for name in courses if courses[name]}

    for runner in runners:
        full_name = runner["name"]
        club = runner["club"]
        start_time = runner["start_time"]
        finish_time = runner["finish_time"]
        splits = runner["splits"]

        split_codes = [s["code"] for s in splits]
        lap_indices = [i for i, code in enumerate(split_codes) if code == lap_control]
        segment_starts = [-1] + lap_indices
        segment_ends = lap_indices + [len(splits)]

        for seg_start, seg_end in zip(segment_starts, segment_ends):
            seg_start_idx = seg_start + 1
            seg_end_idx = seg_end
            segment_codes = split_codes[seg_start_idx:seg_end_idx]
            if not segment_codes:
                continue

            lap_start = start_time if seg_start == -1 else splits[seg_start]["time"]
            lap_end = finish_time if seg_end == len(splits) else splits[seg_end]["time"]

            for course_name, full_control_codes in courses.items():
                if not full_control_codes:
                    continue
                if full_control_codes[-1] != lap_control:
                    return f"<h1>Fel</h1><p>Alla banor måste sluta med samma kodsiffra samt överensstämma med varvningskontrollen</p>"

                match_codes = full_control_codes[:-1]
                if is_subsequence(segment_codes, match_codes):
                    if lap_start is not None and lap_end is not None:
                        results[course_name].append((full_name, club, int(lap_end - lap_start)))

    return results

def extract_results_meos(meos_root):
    event_name = meos_root.findtext("./Name") or ""
    event_date = meos_root.findtext("./Date") or ""

    club_map = {}
    for club in meos_root.findall(".//ClubList/Club"):
        club_id = club.findtext("Id")
        club_name = club.findtext("Name") or ""
        if club_id:
            club_map[club_id] = club_name

    courses = {"A": [], "B": [], "C": [], "D": [], "E": []}
    lap_controls = set()
    for course in meos_root.findall(".//CourseList/Course"):
        name = course.findtext("Name")
        if name in courses:
            controls_text = course.findtext("Controls") or ""
            courses[name] = parse_meos_controls(controls_text)
            ccontrol = course.findtext("oData/CControl")
            if ccontrol:
                lap_controls.add(ccontrol.strip())

    if lap_controls:
        if len(lap_controls) > 1:
            return "<h1>Fel</h1><p>Olika varvningskontroller hittades i MeOS-filen</p>"
        lap_control = lap_controls.pop()
    else:
        last_controls = {codes[-1] for codes in courses.values() if codes}
        if len(last_controls) != 1:
            return "<h1>Fel</h1><p>Kunde inte avgöra varvningskontroll från banorna A-E</p>"
        lap_control = last_controls.pop()

    runners = []
    for runner in meos_root.findall(".//RunnerList/Runner"):
        name = runner.findtext("Name")
        if not name:
            continue
        if "," in name:
            parts = [p.strip() for p in name.split(",", 1)]
            if len(parts) == 2 and parts[0] and parts[1]:
                name = f"{parts[1]} {parts[0]}"
        club_id = runner.findtext("Club") or ""
        club = club_map.get(club_id, "")

        start_text = runner.findtext("Start")
        finish_text = runner.findtext("Finish")
        start_time = int(float(start_text)) if start_text else None
        finish_time = int(float(finish_text)) if finish_text else None

        punches_text = runner.findtext("Card/Punches") or ""
        splits = []
        for token in punches_text.split(";"):
            token = token.strip()
            if not token or "-" not in token:
                continue
            code_part, rest = token.split("-", 1)
            time_part = rest.split("@", 1)[0].split("#", 1)[0]
            try:
                code = code_part.strip()
                time_val = float(time_part)
            except ValueError:
                continue
            splits.append({"code": code, "time": time_val})

        splits.sort(key=lambda s: s["time"])
        runners.append(
            {
                "name": name,
                "club": club,
                "start_time": start_time,
                "finish_time": finish_time,
                "splits": splits,
            }
        )

    result_data = extract_results_from_splits(runners, courses, lap_control)
    if isinstance(result_data, str):
        return result_data

    return result_data, event_name, event_date

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            meos_xml = request.files.get("meos_xml")
            if not meos_xml or not meos_xml.filename:
                return "<h1>Fel</h1><p>MeOS-XML saknas</p>"

            meos_tree = etree.parse(meos_xml)
            meos_root = meos_tree.getroot()
            meos_result = extract_results_meos(meos_root)
            if isinstance(meos_result, str):
                return meos_result
            result_data, event_name, event_date = meos_result

            generated = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            filename = f"{event_date.replace('-', '')[2:]} Resultat per bana {event_name}.html"

            rendered = render_template("result.html", results=result_data, event_name=event_name, event_date=event_date, generated=generated)
            html_file = BytesIO(rendered.encode("utf-8"))
            return send_file(html_file, as_attachment=True, download_name=filename, mimetype="text/html")
        except Exception as e:
            return f"<h1>Fel vid bearbetning:</h1><pre>{str(e)}</pre>"

    return '''
    <!doctype html>
    <title>Skapa Vintercupsresultat per bana</title>
    <h1>Ladda upp MeOS-XML</h1>
    <form method=post enctype=multipart/form-data>
      MeOS XML: <input type=file name=meos_xml><br><br>
      <input type=submit value="Generera HTML">
    </form>
    <p><b>Hjälptext:</b></p>
    <p>Verktyget är byggt efter hur nordöstra Skånes vintercup är utformad. Meos måste ha använts på rätt sätt för att det här ska fungera. david snabel-a vram.se kan dela med sig av instruktioner.</p>
    <p>Exportera en <b>.meosxml</b> från MeOS och ladda upp den här. Banor A–E och varvningskontroll hämtas automatiskt från filen, och resultatlistan genereras direkt.</p>
    <p></p>
    <p><i>David Ek, 2025-04-17</i></p>
    '''

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
