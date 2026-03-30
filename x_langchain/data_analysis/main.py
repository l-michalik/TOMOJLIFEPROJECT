import modal

from langchain_modal import ModalSandbox

app = modal.App.lookup("data-analysis-app", create_if_missing=True)
modal_sandbox = modal.Sandbox.create(app=app)
backend = ModalSandbox(sandbox=modal_sandbox)