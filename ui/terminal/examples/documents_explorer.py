from textual import on
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Mount
from textual.widgets import (
    Tabs,
    Tab,
    Header,
    Footer,
    Label,
    SelectionList,
    Button,
    Input,
    ContentSwitcher,
    Static,
)
from textual.widgets.selection_list import Selection
import asyncio

VALUES = [
    "Falken's Maze",
    "Black Jack",
    "Gin Rummy",
    "Hearts",
    "Bridge",
    "Checkers",
    "Chess",
    "Poker",
    "Fighter Combat",
]


class DocumentsExplorerWidget(Static):
    # CSS_PATH = "style_docs.tcss"

    def compose(self) -> ComposeResult:
        with Vertical(id="main_container"):
            with Horizontal():
                yield SelectionList[str](*[Selection(x, x) for x in VALUES])

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

    def on_mount(self) -> None:
        self.query_one(
            SelectionList
        ).border_title = "All papers in the database"
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

        values = set(selected.selected)
        global VALUES
        VALUES = [x for x in VALUES if x not in values]
        selected.clear_options()
        selected.add_options([Selection(x, x) for x in VALUES])

        self.notify(f"Deleted {len(values)} items from database.")
        await self.my_async_function(selected)

    @on(Button.Pressed, "#add_btn")
    def add_new_item(self) -> None:
        new_val = self.query_one("#new_item_input", Input).value.strip()
        if new_val:
            # Add to the SelectionList
            global VALUES
            VALUES.append(new_val)
            self.query_one(SelectionList).add_option(
                Selection(new_val, new_val)
            )

            # Clear input
            self.query_one("#new_item_input", Input).value = ""
            self.notify(f"Added: {new_val}")

    async def my_async_function(self, items: list[str]) -> None:
        await asyncio.sleep(2)
        self.notify("Action Complete", severity="information")


class MainApp(App):
    CSS_PATH = ["style.tcss", "style_docs.tcss"]

    def compose(self) -> ComposeResult:
        yield Header()

        with Horizontal(id="nav_bar"):
            yield Tabs(
                Tab("Files", id="tab_docs"),
            )
            yield Button("Clear Chat", id="btn_clear_chat", variant="warning")
            yield Button("Clear Agent", id="btn_clear_agent", variant="error")

        with ContentSwitcher(initial="tab_docs"):
            yield DocumentsExplorerWidget(id="tab_docs")

        yield Footer()

    @on(Tabs.TabActivated)
    def switch_tab(self, event: Tabs.TabActivated) -> None:
        self.query_one(ContentSwitcher).current = event.tab.id

    @on(Button.Pressed, "#btn_clear_chat")
    def clear_chat_history(self) -> None:
        # Reach into the ChatbotWidget to clear the log
        log = self.query_one("#chat-log")
        log.remove_children()
        self.notify("Chat cleared")

    @on(Button.Pressed, "#btn_clear_agent")
    def clear_agent_state(self) -> None:
        # Custom logic for your agent reset
        self.notify("Agent history reset", severity="warning")


if __name__ == "__main__":
    MainApp().run()
