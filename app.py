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

def get_courses_from_meos(meos_root):
    courses = {}
    for course_elem in meos_root.findall(".//Course"):
        name = course_elem.findtext("Name")
        control_text = course_elem.findtext("Controls")
        if name in ['A', 'B', 'C', 'D', 'E'] and control_text:
            codes = [code for code in control_text.strip().split(";") if code]
            courses[name] = codes
    return courses

def match_course(name, control_codes, splits, finish_time):
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
    results = {name: [] for name in courses}

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
            match = match_course(course_name, control_codes, splits, finish_time)
            if match:
                _, start, end = match
                results[course_name].append((full_name, end - start))
                break

    return results

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        meos_xml = request.files["meos_xml"]
        result_xml = request.files["result_xml"]

        meos_tree = etree.parse(meos_xml)
        meos_root = meos_tree.getroot()
        courses = get_courses_from_meos(meos_root)

        result_tree = etree.parse(result_xml)
        result_root = result_tree.getroot()

        result_data = extract_results(result_root, courses)

        rendered = render_template("result.html", results=result_data)
        html_file = BytesIO(rendered.encode("utf-8"))
        return send_file(html_file, as_attachment=True, download_name="resultat.html", mimetype="text/html")

    return '''
    <!doctype html>
    <title>Ladda upp MeOS- och resultat-XML</title>
    <h1>Ladda upp meosxml och ejrakabanor.xml</h1>
    <form method=post enctype=multipart/form-data>
      MeOS XML: <input type=file name=meos_xml><br><br>
      Resultat XML: <input type=file name=result_xml><br><br>
      <input type=submit value="Generera HTML">
    </form>
    '''

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
