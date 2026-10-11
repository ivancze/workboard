from .views import filter_query


def board_filter(request):
    """The board's active filter as "?assignee=…", for every link and form
    that leads back to the board, so none of them drops it."""
    return {"filter_query": filter_query(request)}
