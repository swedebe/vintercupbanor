from flask import Flask, render_template, request, send_file
from lxml import etree
from io import BytesIO
from dateutil import parser
import datetime

app = Flask(__name__)

def contains_subsequence(codes, subsequence):
    n = len(subsequence)
    for i in range(len(codes) - n + 1):
        if codes[i:i+n] == subsequence:
            return i, i+n-1
    return None

def parse_course_input(text):
    return [code.strip() for code in text.split(',') if code.strip()]

def extract_results(result_root, courses, lap_control):
    ns = {"iof": "http://www.orienteering.org/datastandard/3.0"}
    results = {name: [] for name in courses if courses[name]}

    for person_result in result_root.findall(".//iof:PersonResult", namespaces=ns):
        person_elem = person_result.find(".//iof:Name", namespaces=ns)
        given = person_elem.findtext("iof:Given", namespaces=ns)
        family = person_elem.findtext("iof:Family", namespaces=ns)
        full_name = f"{given} {family}"

        result_elem = person_result.find(".//iof:Result", namespaces=ns)

        start_elem = person_result.find(".//iof:StartTime", namespaces=ns)
        start_offset = 0
        if start_elem is not None:
            try:
                dt = parser.isoparse(start_elem.text)
                start_offset = dt.hour * 3600 + dt.minute * 60 + dt.second
            except:
                pass

        finish_elem = person_result.find(".//iof:FinishTime", namespaces=ns)
        finish_time = None
        if finish_elem is not None:
            try:
                dt = parser.isoparse(finish_elem.text)
                finish_time = dt.hour * 3600 + dt.minute * 60 + dt.second
            except:
                pass

        splits = []
        for split in result_elem.findall("iof:SplitTime", namespaces=ns):
            code = split.findtext("iof:ControlCode", namespaces=ns)
            time = split.findtext("iof:Time", namespaces=ns)
            status = split.get("status", "")
            if code:
                abs_time = int(time) + start_offset if time else None
                splits.append({"code": code, "time": abs_time, "status": status})

        clean_splits = [s for s in splits if s['status'] not in ("Missing", "Additional") and s['code']]
        split_codes = [s['code'] for s in clean_splits]

        for course_name, full_control_codes in courses.items():
            if not full_control_codes:
                continue
            if full_control_codes[-1] != lap_control:
                return f"<h1>Fel</h1><p>Alla banor måste sluta med samma kodsiffra samt överensstämma med varvningskontrollen</p>"

            match_codes = full_control_codes[:-1]  # exkludera varvningskontrollen
            match = contains_subsequence(split_codes, match_codes)

            while match:
                i_start, i_end = match

                # Starttid: 100 före match eller <StartTime>
                start_time = start_offset
                if i_start > 0 and clean_splits[i_start - 1]['code'] == lap_control:
                    if clean_splits[i_start - 1]['time'] is not None:
                        start_time = clean_splits[i_start - 1]['time']

                # Sluttid: 100 efter match eller <FinishTime>
                end_time = finish_time
                if i_end + 1 < len(clean_splits) and clean_splits[i_end + 1]['code'] == lap_control:
                    if clean_splits[i_end + 1]['time'] is not None:
                        end_time = clean_splits[i_end + 1]['time']

                if start_time is not None and end_time is not None:
                    results[course_name].append((full_name, end_time - start_time))

                for i in range(i_start, i_end + 1):
                    split_codes[i] = "__used__"
                match = contains_subsequence(split_codes, match_codes)

    return results

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            result_xml = request.files["result_xml"]
            result_tree = etree.parse(result_xml)
            result_root = result_tree.getroot()

            lap_control = request.form.get("lap_control", "").strip()
            if not lap_control:
                return "<h1>Fel</h1><p>Varvningskontroll saknas</p>"

            courses = {
                "A": parse_course_input(request.form.get("course_A", "")),
                "B": parse_course_input(request.form.get("course_B", "")),
                "C": parse_course_input(request.form.get("course_C", "")),
                "D": parse_course_input(request.form.get("course_D", "")),
                "E": parse_course_input(request.form.get("course_E", "")),
            }

            result_data = extract_results(result_root, courses, lap_control)
            if isinstance(result_data, str):
                return result_data  # visa ev. felmeddelande

            rendered = render_template("result.html", results=result_data)
            html_file = BytesIO(rendered.encode("utf-8"))
            return send_file(html_file, as_attachment=True, download_name="resultat.html", mimetype="text/html")
        except Exception as e:
            return f"<h1>Fel vid bearbetning:</h1><pre>{str(e)}</pre>"

    return '''
    <!doctype html>
    <title>Resultat per bana</title>
    <h1>Klistra in kontroller för banorna A–E, välj varvningskontroll och ladda upp resultatfil</h1>
    <form method=post enctype=multipart/form-data>
      Varvningskontroll: <input type=text name=lap_control size=10><br><br>
      Bana A: <input type=text name=course_A size=80><br><br>
      Bana B: <input type=text name=course_B size=80><br><br>
      Bana C: <input type=text name=course_C size=80><br><br>
      Bana D: <input type=text name=course_D size=80><br><br>
      Bana E: <input type=text name=course_E size=80><br><br>
      Resultat XML: <input type=file name=result_xml><br><br>
      <input type=submit value="Generera HTML">
    </form>
    '''

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
