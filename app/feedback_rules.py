"""Ownership classification for structured Guest feedback."""


def owner_group(went_well, improvements, safety_status, safety_issues):
    values = {str(x).strip().lower() for x in (*went_well, *improvements, *safety_issues)}
    if safety_status == "Safety issue":
        if values & {"vehicle safety issue"}:
            return "Vendor"
        return "RentaGO Team"
    if values & {"vehicle cleanliness", "vehicle condition"}:
        return "Vendor"
    if values & {"driver punctuality", "driver behaviour", "driving quality"}:
        return "Driver"
    return "RentaGO Team"
