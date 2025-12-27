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
        self._selected_items = set()

    @property
    def documents(self):
        return self._documents

    @property
    def selected_items(self):
        return self._selected_items

    def compose(self) -> ComposeResult:
        with Vertical(id="main_container"):
            with Horizontal():
                with Vertical(id="selectionlist"):
                    yield Input(
                        placeholder="Search papers ...", id="search_input"
                    )
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
                placeholder="Enter path/url to new paper ...",
                id="new_item_input",
            )
            yield Button("Add Paper", id="add_btn")

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
        async def wait_for_servers():
            await asyncio.sleep(2)
            await self.fetch_documents()
            selection_list = self.query_one("#doc_selector", SelectionList)
            selection_list.clear_options()
            selection_list.add_options(
                [Selection(v, v) for v in self._documents.keys()]
            )
            selection_list.border_title = "All papers in the database"

            view = self.query_one("#selected_view")
            view.border_title = "Selected papers to delete from the database"

        asyncio.create_task(wait_for_servers())

    @on(Input.Changed, "#search_input")
    def filter_docs(self, event: Input.Changed) -> None:
        query = event.value.lower()
        selection_list = self.query_one("#doc_selector", SelectionList)

        selection_list.clear_options()
        selection_list.add_options(
            [
                Selection(v, v, (v in self._selected_items))
                for v in self._documents.keys()
                if query in v.lower()
            ]
        )

    @on(Mount)
    @on(SelectionList.SelectedChanged)
    def update_selected_view(self) -> None:
        selection_list = self.query_one("#doc_selector", SelectionList)
        selected_items = set(selection_list.selected)
        unselected_items = {
            item
            for item in selection_list._values.keys()
            if item not in selected_items
        }
        self._selected_items |= selected_items
        self._selected_items -= unselected_items
        formatted_text = "\n".join(
            f"• {item}" for item in self._selected_items
        )
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
        values = self._selected_items
        self.query_one(ContentSwitcher).current = "launch_state"
        self.query_one("#selected_view").update("")

        if not values:
            self.notify("Nothing selected!", severity="error")
            return

        self._documents = {
            k: v for (k, v) in self._documents.items() if k not in values
        }
        selection_list = self.query_one("#doc_selector", SelectionList)
        selection_list.clear_options()
        selection_list.add_options([Selection(x, x) for x in self._documents])
        self._selected_items = {}

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
        is_added = False
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(60.0)
            ) as client:
                response = await client.post(
                    f"{URL}/process_document", json={"doc_path": doc_path}
                )
                if response.is_success:
                    is_added = True
                    # avoid fetching the data
                    document_id = response.json()["document_id"]
                    self._documents[doc_path] = document_id
                    self.notify(f"Added: {doc_path}")
                else:
                    self.notify(f"Could not add {doc_path}", severity="error")
        except Exception as e:
            self.notify(f"Error: {str(e)}", severity="error")

        if not is_added:
            return

        selection_list = self.query_one("#doc_selector", SelectionList)
        selection_list.clear_options()
        selection_list.add_options([Selection(x, x) for x in self._documents])
