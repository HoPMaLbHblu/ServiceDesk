import threading

from django.db import connection


def run_concurrently(fn, args_list):
    """Run ``fn(*args)`` for each args tuple at the same moment, each in its own DB connection.

    Returns a list of results or raised exceptions, in no particular order.
    """
    barrier = threading.Barrier(len(args_list))
    results = []
    lock = threading.Lock()

    def worker(args):
        try:
            barrier.wait()
            outcome = fn(*args)
        except Exception as exc:  # collected for the assertions
            outcome = exc
        finally:
            connection.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker, args=(args,)) for args in args_list]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return results
