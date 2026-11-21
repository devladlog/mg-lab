"""The contract between the data, the training step and the endpoint. Only things known when the ticket is created."""
PRIORITIES = ["P1", "P2", "P3", "P4"]
CATEGORIES = ["network", "access", "hardware", "software", "email"]
CHANNELS = ["phone", "portal", "email"]

CAT_FEATURES = ["priority", "category", "channel"]
NUM_FEATURES = ["hour", "weekday", "text_length"]
FEATURES = CAT_FEATURES + NUM_FEATURES
LABEL = "breached"
RAW_COLUMNS = ["ticket_id", "created_at"] + ["priority", "category", "channel", "text_length"] + [LABEL]
RAW_FILE = "tickets.csv"
