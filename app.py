
from flask import Flask, render_template, request, send_file
from lxml import etree
from io import BytesIO
from dateutil import parser
import tempfile
import datetime

app = Flask(__name__)

# Kontrollkoder för banor
courses = {
    "A": ["101", "102", "103", "104", "105", "106", "107", "100"],
    "B": ["108", "109", "110", "111", "112", "114", "115", "116", "100"],
    "C": ["117", "118", "119", "120", "121", "122", "123", "100"],
    "D": ["124", "125", "128", "129", "130", "131", "132", "133", "100"],
    "E": ["107", "111", "112", "119", "118", "102", "125", "123", "117", "100"]
}

def contains_subsequence(codes, subsequence):
    n = len(subsequence)
    for i in range(len(codes) - n + 1):
        if codes[i:i+n] == subsequence:
            return i, i+n-1
    return None

def find_course_results_ignore_inner_times(root, ns, course_name, control_codes):
    results = []
    core_sequence = control_codes[:-1]
    last_control = control_codes[-1]

    for person_result in root.findall(".//iof:PersonResult", namespaces=ns):
        person_elem = person_result.find(".//iof:Name", namespaces=ns)
        given = person_elem.findtext("iof:Given", namespaces=ns)
        family = person_elem.findtext("iof:Family", namespaces=ns)
        name = f"{given} {family}"

        result_elem = person_result.find(".//iof:Result", namespaces=ns)
        raw_splits = []
        for split in result_elem.findall("iof:SplitTime", namespaces=ns):
            if split.get("status") in ("Missing", "Additional"):
                continue
            code = split.findtext("iof:ControlCode", namespaces=ns)
            time_text = split.findtext("iof:Time", namespaces=ns)
            time = int(time_text) if time_text else None
            if code:
                raw_splits.append({"code": code, "time": time})

        split_codes = [s["code"] for s in raw_splits]
        match = contains_subsequence(split_codes, control_codes)

        if match:
            i_start, i_end = match
            start_time = raw_splits[i_start]["time"]
            end_time = raw_splits[i_end]["time"]
            if start_time is not None and end_time is not None:
                results.append((course_name, name, end_time - start_time))
        else:
            match_core = contains_subsequence(split_codes, core_sequence)
            finish_elem = person_result.find(".//iof:FinishTime", namespaces=ns)
            if match_core and finish_elem is not None:
                try:
                    finish_dt = parser.isoparse(finish_elem.text)
                    finish_time = finish_dt.hour * 3600 + finish_dt.minute * 60 + finish_dt.second
                    i_start, _ = match_core
                    start_time = raw_splits[i_start]["time"]
                    if start_time is not None:
                        results.append((course_name, name, finish_time - start_time))
                except:
                    continue
    return results

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        result_xml = request.files["result_xml"]
        tree = etree.parse(result_xml)
        root = tree.getroot()
        ns = {"iof": "http://www.orienteering.org/datastandard/3.0"}

        all_results = []
        for cname, controls in courses.items():
            res = find_course_results_ignore_inner_times(root, ns, cname, controls)
            res_sorted = sorted(res, key=lambda x: x[2])
            for i, (course, name, time) in enumerate(res_sorted, 1):
                all_results.append((course, i, name, str(datetime.timedelta(seconds=time))))
        
        rendered = render_template("result.html", results=all_results)
        html_file = BytesIO(rendered.encode("utf-8"))
        return send_file(html_file, as_attachment=True, download_name="resultat.html", mimetype="text/html")

    return '''
    <!doctype html>
    <title>Ladda upp resultat-XML</title>
    <h1>Ladda upp ejrakabanor.xml</h1>
    <form method=post enctype=multipart/form-data>
      <input type=file name=result_xml>
      <input type=submit value="Generera HTML">
    </form>
    '''

if __name__ == "__main__":
    app.run(debug=True)
