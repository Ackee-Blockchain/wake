import time
import logging

from pytypes.hello_world import HelloWorld

from pathlib import Path

logging.basicConfig(filename='test.log', level=logging.DEBUG)

def test_hello_world():
    start_time = time.time()
    hello: HelloWorld = HelloWorld.deploy()
    counter_val = 0
    for _ in range(100):
        counter_val = hello.incrementCounter()
        hello.helloWorld()
    total_time = time.time() - start_time

    path = Path("./output.txt")
    if path.exists():
        with path.open('a') as f:
            f.write(f"total time: {total_time}, counter: {counter_val}\n")
    else:
        path.touch()
        path.write_text(f"total time: {total_time}\n")


test_hello_world()