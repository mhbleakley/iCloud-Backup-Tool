import argparse
import os
import json
from collections import defaultdict
from pathlib import Path
from tqdm import tqdm
from PIL import Image, ImageDraw
import math
import folium
import cv2
import uuid
import csv

PICTURE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic'}
VIDEO_EXTENSIONS = {'.mov', '.mp4', '.avi', '.hevc'}

MAP_WIDTH = 2048
MAP_HEIGHT = 1024

def find_corresponding_image(all_files, source_filename):
    for file, full_path in all_files:
        if file == source_filename:
            return full_path
    return None

def draw_all_bboxes(target_dir, output_dir, output_format="jpg"):
    all_files = get_all_files(target_dir)
    image_map = {file: path for file, path in all_files if classify_file_type_by_ext(file) == 'picture'}
    os.makedirs(output_dir, exist_ok=True)

    csv_path = os.path.join(output_dir, "boundingboxes.csv")
    csv_fields = ['uuid', 'filename', 'export_path', 'date', 'name', 'x', 'y', 'h', 'w']
    rows = []

    for file, full_path in tqdm(all_files, desc="Scanning for bounding boxes"):
        if not file.lower().endswith('.json'):
            continue

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if not isinstance(data, list):
                continue

            for item in data:
                region_info = item.get("XMP-mwg-rs:RegionInfo")
                if not region_info:
                    continue

                regions = region_info.get("RegionList", [])
                dimensions = region_info.get("AppliedToDimensions", {})
                img_w = dimensions.get("W")
                img_h = dimensions.get("H")
                if not regions or not img_w or not img_h:
                    continue

                source_file = item.get("SourceFile")
                image_path = image_map.get(source_file)
                if not image_path:
                    continue

                image = cv2.imread(image_path)
                if image is None:
                    print(f"Could not read: {image_path}")
                    continue

                valid_rows = []
                for region in tqdm(regions, desc=f"Drawing boxes for {source_file}", leave=False):
                    area = region.get("Area", {})
                    if area.get("Unit") != "normalized":
                        continue

                    x_center = area.get("X")
                    y_center = area.get("Y")
                    box_w = area.get("W")
                    box_h = area.get("H")

                    if None in (x_center, y_center, box_w, box_h):
                        continue

                    x1 = int((x_center - box_w / 2) * img_w)
                    y1 = int((y_center - box_h / 2) * img_h)
                    x2 = int((x_center + box_w / 2) * img_w)
                    y2 = int((y_center + box_h / 2) * img_h)

                    cv2.rectangle(image, (x1, y1), (x2, y2), color=(0, 0, 255), thickness=2)

                    name = region.get("Name", "")

                    row = {
                        'uuid': str(uuid.uuid4()),
                        'filename': source_file,
                        'export_path': os.path.join(output_dir, Path(source_file).stem + f".{output_format}"),
                        'date': item.get("EXIF:DateTimeOriginal", ""),
                        'name': name,
                        'x': x1,
                        'y': y1,
                        'h': y2 - y1,
                        'w': x2 - x1
                    }
                    valid_rows.append(row)

                if valid_rows:
                    rows.extend(valid_rows)

                    output_file = Path(source_file).stem + f".{output_format}"
                    output_path = os.path.join(output_dir, output_file)

                    if output_format == "jpg":
                        cv2.imwrite(output_path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                    elif output_format == "png":
                        cv2.imwrite(output_path, image, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])
                    elif output_format == "heic":
                        print(f"HEIC output not supported yet: skipping {source_file}")
        except Exception:
            continue

    # Write the CSV
    with open(csv_path, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Bounding boxes written to {csv_path}")

def mercator_projection(lat, lon, width, height):
    x = (lon + 180.0) * (width / 360.0)
    lat_rad = math.radians(lat)
    y = (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * height
    return int(x), int(y)

def generate_map(target_dir, output_path):
    all_files = get_all_files(target_dir)
    coordinates = []

    for file, full_path in tqdm(all_files, desc="Extracting coordinates"):
        if not file.lower().endswith('.json'):
            continue

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                for item in data:
                    lat = item.get("EXIF:GPSLatitude")
                    lon = item.get("EXIF:GPSLongitude")
                    if lat is not None and lon is not None:
                        try:
                            coordinates.append((float(lat), float(lon)))
                        except (ValueError, TypeError):
                            continue
        except Exception:
            continue

    if not coordinates:
        print("No GPS coordinates found.")
        return

    avg_lat = sum(lat for lat, _ in coordinates) / len(coordinates)
    avg_lon = sum(lon for _, lon in coordinates) / len(coordinates)

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=4, tiles="OpenStreetMap")

    for lat, lon in tqdm(coordinates, desc="Placing markers"):
        folium.CircleMarker(
            location=[lat, lon],
            radius=2,
            color='red',
            fill=True,
            fill_opacity=0.7
        ).add_to(m)

    m.save(output_path)

def classify_file_type_by_ext(filename):
    ext = Path(filename).suffix.lower()
    if ext in PICTURE_EXTENSIONS:
        return 'picture'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    return None

def get_all_files(target_dir):
    all_files = []
    for root, _, files in os.walk(target_dir):
        for file in files:
            full_path = os.path.join(root, file)
            all_files.append((file, full_path))
    return all_files

def extract_keys(obj, prefix=''):
    keys = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            full_key = f"{prefix}.{k}" if prefix else k
            keys.add(full_key)
            keys.update(extract_keys(v, full_key))
    elif isinstance(obj, list):
        for item in obj:
            keys.update(extract_keys(item, prefix))
    return keys

def summarize_directory(target_dir):
    counts = defaultdict(int)
    picture_keys = set()
    video_keys = set()

    all_files = get_all_files(target_dir)

    for file, _ in tqdm(all_files, desc="Classifying files"):
        file_type = classify_file_type_by_ext(file)
        if file_type:
            counts[file_type] += 1
        elif not file.lower().endswith('.json'):
            counts['other'] += 1

    for file, full_path in tqdm(all_files, desc="Parsing JSONs"):
        if not file.lower().endswith('.json'):
            continue

        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            source_file = None
            keys = extract_keys(data)

            if isinstance(data, dict):
                source_file = data.get("SourceFile")
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and not source_file:
                        source_file = item.get("SourceFile")

            if source_file:
                file_type = classify_file_type_by_ext(source_file)
                if file_type == 'picture':
                    picture_keys.update(keys)
                elif file_type == 'video':
                    video_keys.update(keys)

        except Exception:
            continue

    return counts, sorted(picture_keys), sorted(video_keys)

def save_summary(summary_path, counts, picture_keys, video_keys):
    with open(summary_path, 'w') as f:
        f.write(f"total number of pictures: {counts['picture']}\n")
        f.write(f"total number of videos: {counts['video']}\n")
        f.write(f"total number of other file types: {counts['other']}\n\n")
        f.write("json keys associated with pictures:\n")
        for key in picture_keys:
            f.write(f"{key}\n")
        f.write("\njson keys associated with videos:\n")
        for key in video_keys:
            f.write(f"{key}\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-t", "--target", required=True, help="Target iCloud directory")
    parser.add_argument("-s", "--summary", action="store_true", help="Generate summary of target directory")
    parser.add_argument("-m", "--map", action="store_true", help="Generate GPS map of coordinates from JSON files")
    parser.add_argument("-b", "--bbox", action="store_true", help="Draw bounding boxes on all images with regions")
    parser.add_argument("--output-format", choices=["jpg", "png", "heic"], default="jpg", help="Output format for bbox images")

    args = parser.parse_args()

    if args.summary:
        counts, picture_keys, video_keys = summarize_directory(args.target)
        print(f"total number of pictures: {counts['picture']}")
        print(f"total number of videos: {counts['video']}")
        print(f"total number of other file types: {counts['other']}\n")
        print("json keys associated with pictures:")
        for key in picture_keys:
            print(key)
        print("\njson keys associated with videos:")
        for key in video_keys:
            print(key)
        analysis_dir = os.path.join(args.target, 'analysis')
        os.makedirs(analysis_dir, exist_ok=True)
        summary_path = os.path.join(analysis_dir, 'summary.txt')
        save_summary(summary_path, counts, picture_keys, video_keys)

    if args.map:
        analysis_dir = os.path.join(args.target, 'analysis')
        os.makedirs(analysis_dir, exist_ok=True)
        map_path = os.path.join(analysis_dir, 'map.html')
        generate_map(args.target, map_path)

    if args.bbox:
        output_dir = os.path.join(args.target, 'analysis', 'bounding-boxes')
        draw_all_bboxes(args.target, output_dir, output_format=args.output_format)

if __name__ == "__main__":
    main()
