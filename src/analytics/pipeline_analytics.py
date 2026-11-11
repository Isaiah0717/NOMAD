import pandas as pd

from src.database import get_database_connection


def load_pipeline_runs():
    query = """
        SELECT *
        FROM pipeline_runs
        ORDER BY started_at DESC;
    """

    with get_database_connection() as connection:
        df = pd.read_sql(query, connection)

    return df


def build_operations_report(df):
    df = df.copy()

    # Calculate runtime for every completed pipeline run.
    df["runtime_seconds"] = (df["completed_at"] - df["started_at"]).dt.total_seconds()

    total_runs = len(df)
    successful_runs = (df["status"] == "SUCCESS").sum()
    failed_runs = (df["status"] == "FAILED").sum()

    success_rate = successful_runs / total_runs * 100 if total_runs > 0 else 0

    total_records_read = df["records_read"].fillna(0).sum()
    total_records_loaded = df["records_loaded"].fillna(0).sum()

    load_rate = (
        total_records_loaded / total_records_read * 100 if total_records_read > 0 else 0
    )

    average_runtime = df["runtime_seconds"].mean()

    print("\nNOMAD OPERATIONS REPORT")
    print("=======================")

    print(f"\nTotal pipeline runs: {total_runs}")
    print(f"Successful runs:     {successful_runs}")
    print(f"Failed runs:         {failed_runs}")
    print(f"Success rate:        {success_rate:.2f}%")

    print("\nDATA MOVEMENT")
    print("-------------")
    print(f"Records read:        {int(total_records_read)}")
    print(f"Records loaded:      {int(total_records_loaded)}")
    print(f"Load rate:           {load_rate:.2f}%")

    print("\nRUNS BY SOURCE TYPE")
    print("-------------------")
    print(df["source_type"].value_counts())

    print("\nPERFORMANCE")
    print("-----------")
    print(f"Average runtime:     {average_runtime:.3f} seconds")

    completed_runs = df.dropna(subset=["runtime_seconds"])

    if not completed_runs.empty:
        slowest_run = completed_runs.loc[completed_runs["runtime_seconds"].idxmax()]

        print(
            f"Slowest run:         #{slowest_run['run_id']} "
            f"({slowest_run['runtime_seconds']:.3f} seconds)"
        )

    quality_runs = df.dropna(subset=["quality_score"])

    print("\nDATA QUALITY")
    print("------------")

    if quality_runs.empty:
        print("No quality metrics recorded yet.")
    else:
        valid_records = quality_runs["records_valid"].fillna(0).sum()
        rejected_records = quality_runs["records_rejected"].fillna(0).sum()
        average_quality = quality_runs["quality_score"].mean()

        print(f"Measured runs:       {len(quality_runs)}")
        print(f"Valid records:       {int(valid_records)}")
        print(f"Rejected records:    {int(rejected_records)}")
        print(f"Average quality:     {average_quality:.2f}%")

    print("\nFAILURE HISTORY")
    print("---------------")

    failures = df[df["status"] == "FAILED"]

    if failures.empty:
        print("No failed runs recorded.")
    else:
        for _, failure in failures.iterrows():
            print(
                f"Run #{failure['run_id']} | "
                f"{failure['source_type']} | "
                f"{failure['source_name']}"
            )

            print(f"  Error: {failure['error_message']}")


if __name__ == "__main__":
    pipeline_runs = load_pipeline_runs()
    build_operations_report(pipeline_runs)
