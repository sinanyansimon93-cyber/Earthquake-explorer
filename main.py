import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen


API_URL = (
    "https://earthquake.usgs.gov/earthquakes/"
    "feed/v1.0/summary/2.5_month.geojson"
)

PROJECT_ID = "eartquake-bigquery"
DATASET_ID = f"{PROJECT_ID}.someidforbigquery"
TABLE_ID = f"{DATASET_ID}.earthquakes"

PROJECT_FOLDER = Path(__file__).resolve().parent
FETCH_INTERVAL_SECONDS = 3 * 24 * 60 * 60


def fetch_earthquakes():
    """Fetch all earthquakes in the magnitude 2.5+, past-30-days feed."""
    with urlopen(API_URL, timeout=60) as response:
        data = json.load(response)

    rows = []

    for event in data["features"]:
        properties = event["properties"]

        if properties.get("type") != "earthquake":
            continue

        longitude, latitude, depth = event["geometry"]["coordinates"]

        event_time = datetime.fromtimestamp(
            properties["time"] / 1000,
            tz=timezone.utc,
        )

        rows.append({
            "earthquake_id": event["id"],
            "event_time": event_time.isoformat(),
            "place": properties.get("place"),
            "magnitude": properties.get("mag"),
            "longitude": longitude,
            "latitude": latitude,
            "depth_km": depth,
        })

    return rows


def save_to_bigquery(rows):
    """Insert new earthquake IDs and update matching records."""
    from google.cloud import bigquery

    if not rows:
        return 0

    unique_rows = list({
        row["earthquake_id"]: row
        for row in rows
    }.values())

    with bigquery.Client(project=PROJECT_ID) as client:
        dataset = client.get_dataset(DATASET_ID)

        sql = f"""
        MERGE `{TABLE_ID}` AS target
        USING (
            SELECT
                JSON_VALUE(item, '$.earthquake_id') AS earthquake_id,
                CAST(JSON_VALUE(item, '$.event_time') AS TIMESTAMP)
                    AS event_time,
                JSON_VALUE(item, '$.place') AS place,
                CAST(JSON_VALUE(item, '$.magnitude') AS FLOAT64)
                    AS magnitude,
                CAST(JSON_VALUE(item, '$.longitude') AS FLOAT64)
                    AS longitude,
                CAST(JSON_VALUE(item, '$.latitude') AS FLOAT64)
                    AS latitude,
                CAST(JSON_VALUE(item, '$.depth_km') AS FLOAT64)
                    AS depth_km
            FROM UNNEST(JSON_QUERY_ARRAY(@payload)) AS item
        ) AS source
        ON target.earthquake_id = source.earthquake_id

        WHEN MATCHED THEN
            UPDATE SET
                event_time = source.event_time,
                place = source.place,
                magnitude = source.magnitude,
                longitude = source.longitude,
                latitude = source.latitude,
                depth_km = source.depth_km

        WHEN NOT MATCHED THEN
            INSERT (
                earthquake_id,
                event_time,
                place,
                magnitude,
                longitude,
                latitude,
                depth_km
            )
            VALUES (
                source.earthquake_id,
                source.event_time,
                source.place,
                source.magnitude,
                source.longitude,
                source.latitude,
                source.depth_km
            )
        """

        config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "payload",
                    "STRING",
                    json.dumps(unique_rows, allow_nan=False),
                )
            ]
        )

        client.query(
            sql,
            job_config=config,
            location=dataset.location,
        ).result()

    return len(unique_rows)


def save_snapshot(rows):
    """Save all fetched rows to a JSON file beside this script."""
    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%d_%H%M%S_%f"
    )
    filename = PROJECT_FOLDER / f"earthquakes_{timestamp}.json"

    with filename.open("w", encoding="utf-8") as file:
        json.dump(
            rows,
            file,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    return filename


def main():
    """Fetch, display, and save a local snapshot."""
    print("Fetching earthquake data...")
    earthquakes = fetch_earthquakes()

    print(f"Received {len(earthquakes)} earthquakes.")

    for row in earthquakes:
        print(
            f"M {row['magnitude']} | {row['place']} | "
            f"Depth: {row['depth_km']} km | {row['event_time']}"
        )

    filename = save_snapshot(earthquakes)
    print(f"\nSaved all {len(earthquakes)} earthquakes to {filename}")


if __name__ == "__main__":
    try:
        while True:
            try:
                main()
            except Exception as error:
                print(f"Collection failed: {error}")

            print("\nNext fetch in 3 days. Press Ctrl+C to stop.")
            time.sleep(FETCH_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\nStopped.")