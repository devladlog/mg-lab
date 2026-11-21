"""teamsfake: an in-memory Microsoft Teams (channels, Flow bot chats, wait-for-response cards, @mention tokens,
connector throttling) for testing Teams cloud flows locally. Test double, not Teams."""
from .scenario import (ONCALL_CHANNEL, PARAMS, PRIVATE_CHANNEL, TEAM_ID, Dispatch, Helpdesk, default_teams,
                       it_request)
from .teams import Response, Teams

__all__ = ["ONCALL_CHANNEL", "PARAMS", "PRIVATE_CHANNEL", "TEAM_ID", "Dispatch", "Helpdesk", "default_teams",
           "it_request", "Response", "Teams"]
