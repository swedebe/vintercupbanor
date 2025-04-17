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

def match_course(name, control_codes, splits, finish_time):
    if not control_codes:
        return None

    raw_splits = [s for s in splits if s['status'] not in ("Missing", "Additional")]
    split_codes = [s['code'] for s in raw_splits]

    match = contains_subsequence(split_codes, control_codes)
    if match:
        i_start, i_end = match
        start_time = raw_splits[i_start]["time"]
        end_time = raw_splits[i_end]["time"]
        if start_time is not None and end_time is not None:
            return name, start_time, end_time
    else:
        match_core = contains_subsequence(split_codes, control_codes[:-1])
        if match_core and finish_time is not None:
            i_start, _ = match_core
            start_time = raw_splits[i_start]["time"]
            if start_time is not None:
                return name, start_time, finish_time
    return None

def extract_results(result_root, courses):
    ns = {"iof": "http://www.orienteering.org/datastandard/3.0"}
    results = {name: [] for name in courses if courses[name]}

    for person_result in result_root.findall(".//iof:PersonResult", namespaces=ns):
        person_elem = person_result.find(".//iof:Name", namespaces=ns)
        given = person_elem.findtext("iof:Given", namespaces=ns)
        family = person_elem.findtext("iof:Family", namespaces=ns)
        full_name = f"{given} {family}"

        result_elem = person_result.find(".//iof:Result", namespaces=ns)
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
            splits.append({"code": code, "time": int(time) if time else None, "status": status})

        for course_name, control_codes in courses.items():
            if not control_codes:
                continue
            match = match_course(course_name, control_codes, splits, finish_time)
            if match:
                _, start, end = match
                results[course_name].append((full_name, end - start))
                break

    return results

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        try:
            result_xml = request.files["result_xml"]
            result_tree = etree.parse(result_xml)
            result_root = result_tree.getroot()

            courses = {
                "A": parse_course_input(request.form.get("course_A", "")),
                "B": parse_course_input(request.form.get("course_B", "")),
                "C": parse_course_input(request.form.get("course_C", "")),
                "D": parse_course_input(request.form.get("course_D", "")),
                "E": parse_course_input(request.form.get("course_E", "")),
            }

            result_data = extract_results(result_root, courses)

            rendered = render_template("result.html", results=result_data)
            html_file = BytesIO(rendered.encode("utf-8"))
            return send_file(html_file, as_attachment=True, download_name="resultat.html", mimetype="text/html")
        except Exception as e:
            return f"<h1>Fel vid bearbetning:</h1><pre>{str(e)}</pre>"

    return '''
    <!doctype html>
    <title>Resultat per bana</title>
    <h1>Klistra in kontroller för banorna A–E och ladda upp resultatfil</h1>
    <form method=post enctype=multipart/form-data>
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
