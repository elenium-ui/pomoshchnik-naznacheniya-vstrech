from aiogram.fsm.state import State, StatesGroup


class BookingForm(StatesGroup):
    name = State()
    topic = State()
    meeting_format = State()
    duration = State()
    email = State()
    phone_if_needed = State()
    comment = State()
    slot_selection = State()
    reschedule_slot_selection = State()
    admin_close_date = State()
    admin_reopen_day = State()
    admin_add_block = State()
    admin_set_min_lead = State()
    admin_set_window = State()
    admin_clear_windows = State()
    admin_one_time_window = State()
    admin_delete_one_time_window = State()
    admin_block_user = State()
    admin_unblock_user = State()
