import modal
import csv
import io

from langchain_modal import ModalSandbox

app = modal.App.lookup("data-analysis-app", create_if_missing=True)

# Create the sandbox
modal_sandbox = modal.Sandbox.create(app=app)
backend = ModalSandbox(sandbox=modal_sandbox)

# Create sample sales data
data = [
    ["Date", "Product", "Units Sold", "Revenue"],
    ["2025-08-01", "Widget A", 10, 250],
    ["2025-08-02", "Widget B", 5, 125],
    ["2025-08-03", "Widget A", 7, 175],
    ["2025-08-04", "Widget C", 3, 90],
    ["2025-08-05", "Widget B", 8, 200],
]

# Convert to CSV bytes
text_buf = io.StringIO()
writer = csv.writer(text_buf)
writer.writerows(data)
csv_bytes = text_buf.getvalue().encode("utf-8")
text_buf.close()

# === Modern way: use filesystem.write_bytes ===
modal_sandbox.filesystem.write_bytes(
    csv_bytes,
    "/home/daytona/data/sales_data.csv"   # parent dirs are created automatically
)
