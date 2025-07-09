import os
import csv
import argparse
from datetime import datetime, timedelta
from tqdm import tqdm
import osxphotos

# /Volumes/Crucial X9/martin/icloud-photos

CSV_FILENAME = "downloaded_photos.csv"
CSV_COLUMNS = ["uuid", "filename", "export_path", "date"]

def parse_args():
    parser = argparse.ArgumentParser(description="Export photos by month from Photos library")
    parser.add_argument("start_date", help="Start date in YYYY-MM-DD format")
    parser.add_argument("end_date", help="End date in YYYY-MM-DD format")
    parser.add_argument("target_dir", help="Top-level export directory")
    return parser.parse_args()

def month_range(start, end):
    current = datetime(start.year, start.month, 1)
    while current <= end:
        yield current
        if current.month == 12:
            current = datetime(current.year + 1, 1, 1)
        else:
            current = datetime(current.year, current.month + 1, 1)

def load_existing_records(csv_path):
    records = set()
    if not os.path.exists(csv_path):
        return records
    with open(csv_path, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.add(row["uuid"])
    return records

def append_to_csv(csv_path, rows):
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        writer.writerows(rows)

def ensure_directory(path):
    os.makedirs(path, exist_ok=True)

def main():
    args = parse_args()

    try:
        start_dt = datetime.strptime(args.start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(args.end_date, "%Y-%m-%d")
    except ValueError:
        print("Invalid date format. Use YYYY-MM-DD")
        return

    if start_dt > end_dt:
        print("Start date must be before end date.")
        return

    ensure_directory(args.target_dir)
    csv_path = os.path.join(args.target_dir, CSV_FILENAME)
    downloaded_uuids = load_existing_records(csv_path)

    photosdb = osxphotos.PhotosDB()
    all_photos = photosdb.photos()

    for month_start in month_range(start_dt, end_dt):
        month_end = datetime(month_start.year + (month_start.month // 12),
                             (month_start.month % 12) + 1, 1)
        if month_end > end_dt:
            month_end = end_dt + timedelta(days=1)

        photos = [
            p for p in all_photos
            if month_start <= p.date.replace(tzinfo=None) < month_end
            and p.uuid not in downloaded_uuids
        ]

        if not photos:
            continue

        export_folder = os.path.join(args.target_dir, month_start.strftime("%y-%m"))
        ensure_directory(export_folder)

        print(f"Exporting {len(photos)} new photos from {month_start.strftime('%Y-%m')} to {export_folder}")

        new_records = []

        for photo in tqdm(photos, unit="photo"):
            results = photo.export(
                export_folder,
                edited=False,
                sidecar_json=True,
                overwrite=True,
                export_as_hardlink=False,
                increment=False,
                use_photos_export=True
            )

            if not results:
                continue

            export_file = results[0]
            record = {
                "uuid": photo.uuid,
                "filename": os.path.basename(export_file),
                "export_path": export_file,
                "date": photo.date.strftime("%Y-%m-%d %H:%M:%S")
            }
            new_records.append(record)

        append_to_csv(csv_path, new_records)
        print(f"Completed {month_start.strftime('%Y-%m')}")

if __name__ == "__main__":
    main()
