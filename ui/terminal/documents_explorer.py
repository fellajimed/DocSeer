import asyncio
import httpx
from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Mount
from textual.widgets import (
    Label,
    SelectionList,
    Button,
    Input,
    ContentSwitcher,
    Static,
)
from textual.widgets.selection_list import Selection

URL = "http://localhost:8000"


class DocumentsExplorerWidget(Static):
    can_focus = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # mappping source to id
        self._documents = dict()

    @property
    def documents(self):
        return self._documents

    def compose(self) -> ComposeResult:
        with Vertical(id="main_container"):
            with Horizontal():
                yield SelectionList[str](id="doc_selector")

                with Vertical(id="sidebar"):
                    yield Label(id="selected_view")

                    with Vertical(id="action_area"):
                        with ContentSwitcher(initial="launch_state"):
                            yield Button(
                                "Delete Selected",
                                variant="primary",
                                id="launch_state",
                            )

                            with Vertical(id="confirm_state"):
                                yield Label("Confirm?", id="confirm_msg")
                                with Horizontal(id="button_row"):
                                    yield Button(
                                        "Yes", variant="success", id="yes"
                                    )
                                    yield Button(
                                        "No!!", variant="error", id="no"
                                    )
            with Horizontal(id="input_bar"):
                yield Input(
                    placeholder="Enter new item name...", id="new_item_input"
                )
                yield Button("Add Element", id="add_btn")

    async def fetch_documents(self):
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0)
            ) as client:
                response = await client.get(f"{URL}/get_processed_documents")
                self._documents = response.json()
        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")

    async def on_mount(self) -> None:
        await self.fetch_documents()
        selection_list = self.query_one("#doc_selector", SelectionList)
        selection_list.clear_options()
        selection_list.add_options(
            [Selection(v, v) for v in self._documents.keys()]
        )
        selection_list.border_title = "All papers in the database"

        view = self.query_one("#selected_view")
        view.border_title = "Selected papers to delete from the database"

    @on(Mount)
    @on(SelectionList.SelectedChanged)
    def update_selected_view(self) -> None:
        selected_items = self.query_one(SelectionList).selected
        formatted_text = "\n".join(f"• {item}" for item in selected_items)
        self.query_one("#selected_view").update(formatted_text)

    @on(Button.Pressed, "#launch_state")
    def show_confirm(self) -> None:
        self.query_one(ContentSwitcher).current = "confirm_state"

    @on(Button.Pressed, "#no")
    def hide_confirm(self) -> None:
        # Switch back to the launch button
        self.query_one(ContentSwitcher).current = "launch_state"

    @on(Button.Pressed, "#yes")
    async def handle_submit(self) -> None:
        selected = self.query_one(SelectionList)
        values = set(selected.selected)
        self.query_one(ContentSwitcher).current = "launch_state"
        self.query_one("#selected_view").update("")

        if not values:
            self.notify("Nothing selected!", severity="error")
            return

        self._documents = {
            k: v for (k, v) in self._documents.items() if k not in values
        }
        selected.clear_options()
        selected.add_options([Selection(x, x) for x in self._documents])

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0)
            ) as client:
                tasks = [
                    client.request(
                        "DELETE",
                        f"{URL}/delete_document",
                        json={"doc_path": p},
                    )
                    for p in values
                ]
                responses = await asyncio.gather(*tasks)
                for doc_path, response in zip(values, responses):
                    detail = response.json()["detail"]
                    severity = "warning" if "not" in detail else "information"
                    self.notify(
                        f"Source: {doc_path}\nStatus: {detail}",
                        severity=severity,
                    )
        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")

        self.notify(f"Deleted {len(values)} items from database.")

    @on(Button.Pressed, "#add_btn")
    async def add_new_item(self) -> None:
        doc_path = self.query_one("#new_item_input", Input).value.strip()
        if not doc_path:
            return

        input_block = self.query_one("#new_item_input", Input)
        input_block.value = ""
        self.focus(input_block)

        doc_path = doc_path.strip()
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0)
            ) as client:
                response = await client.post(
                    f"{URL}/process_document", json={"doc_path": doc_path}
                )
                if response.is_success:
                    # avoid fetching the data
                    document_id = response.json()["document_id"]
                    self._documents[doc_path] = document_id
                else:
                    self.notify(f"Could not add {doc_path}", severity="error")
        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")

        selected = self.query_one(SelectionList)
        selected.clear_options()
        selected.add_options([Selection(x, x) for x in self._documents])

        self.notify(f"Added: {doc_path}")
