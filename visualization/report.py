# FIRMA ELIAD - NON MODIFICABILE
from rich.console import Console
from rich.table import Table

console = Console()


def show_report(df):
    table = Table(title="Cognitive Attack Surface")

    table.add_column("User")
    table.add_column("Risk Score")
    table.add_column("Top Driver")

    for _, row in df.iterrows():
        table.add_row(
            str(row.get("user", "n/a")),
            f"{row['risk_score']:.2f}",
            str(row.get("top_risk_driver", "n/a")),
        )

    console.print(table)

