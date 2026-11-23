from main import fetch_earthquakes, save_to_bigquery


def main():
    print("Получаем данные USGS...", flush=True)
    rows = fetch_earthquakes()

    print(f"Получено записей: {len(rows)}", flush=True)
    saved_count = save_to_bigquery(rows)

    print(
        f"Синхронизировано с BigQuery: {saved_count}",
        flush=True,
    )


if __name__ == "__main__":
    main()