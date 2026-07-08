import db

# Records a single user's id/username. Called opportunistically (e.g. per-message)
# since bulk-fetching all guild members requires the privileged Members intent,
# which this bot does not request.
def record_known_user(user):
    db.upsert_known_user(user.id, user.name)

# Get known users as "username (userID)" strings
def get_known_users():
    return db.get_known_users()
