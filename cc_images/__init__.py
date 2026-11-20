import multiprocessing

# Build and push tasks run in forked worker processes. Python 3.14 changed the default start
# method on Linux from "fork" to "forkserver", which re-imports the unguarded cc-images.py
# entrypoint while bootstrapping and fails with "An attempt has been made to start a new process
# before the current process has finished its bootstrapping phase". Pin "fork" so the manager
# and the workers start the same way on every Python version.
process_context = multiprocessing.get_context("fork")
process_manager = process_context.Manager()
