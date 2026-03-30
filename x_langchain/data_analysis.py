import modal
import csv
import io

from langchain_modal import ModalSandbox

app = modal.App.lookup("data-analysis", create_if_missing=True)
sb = modal.Sandbox.create(app=app)
backend = ModalSandbox(sandbox=sb)

# Sample data
data = [
    ["Date", "Product", "Units Sold", "Revenue"],
    ["2025-08-01", "Widget A", 10, 250],
    ["2025-08-02", "Widget B", 5, 125],
    ["2025-08-03", "Widget A", 7, 175],
    ["2025-08-04", "Widget C", 3, 90],
    ["2025-08-05", "Widget B", 8, 200],
]

# Create CSV bytes
buf = io.StringIO()
csv.writer(buf).writerows(data)
csv_bytes = buf.getvalue().encode("utf-8")

# Fixed upload - correct argument order
sb.filesystem.write_bytes(csv_bytes, "/home/daytona/data/sales_data.csv")

print("✅ File uploaded!")