import csv
import json
import sys

# A tool used to convert a csv of the segmentation map values into their colors.
#
# CLI use (paths are cwd-relative, so run from the directory holding the csv):
#     python seg_map_importer.py
#     python seg_map_importer.py seg_map.csv seg_map.json
#     python seg_map_importer.py /path/to/in.csv /path/to/out.json
#
# Library use (e.g. seg_map page regenerates a missing seg_map.json):
#     from forge.extras.seg_map_importer import convert_csv_to_json
#     convert_csv_to_json('seg_map.csv', 'seg_map.json')

DEFAULT_IN_FILE = 'seg_map.csv'
DEFAULT_OUT_FILE = 'seg_map.json'
ORIGIN_URL = 'https://docs.google.com/spreadsheets/d/1se8YEtb2detS7OuPE86fXGyD269pMycAWe2mtKUj2W8/edit#gid=0'


def convert_csv_to_json(in_file_path=DEFAULT_IN_FILE, out_file_path=DEFAULT_OUT_FILE):
    """Convert the segmentation color-table CSV into the JSON map. Returns out path."""
    data = {
        "origin": ORIGIN_URL,
        "key": []
    }
    with open(in_file_path, 'r', newline='', encoding='utf-8') as file:
        csv_file = csv.reader(file)
        for line_num, line in enumerate(csv_file):
            if line_num == 0:
                continue
            rgb_str_split = line[5].replace('(', '').replace(')', '').replace(' ', '').split(',')
            rgb_parsed = list(map(lambda x: int(x), rgb_str_split)) # convert "(120, 120, 120)" into [120, 120, 120]
            line_values = {
                'rgb': rgb_parsed,
                'hex': line[6],
                'desc': line[8].split(';')
            }
            data['key'].append(line_values)


    with open(out_file_path, 'w', encoding='utf-8') as file:
        file.write(json.dumps(data, indent=4))
    return out_file_path


if __name__ == '__main__':
    in_arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IN_FILE
    out_arg = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT_FILE
    convert_csv_to_json(in_arg, out_arg)
