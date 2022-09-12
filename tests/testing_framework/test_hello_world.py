import time
import logging

from typing import overload

from tests.pytypes.pytypes.hello_world import HelloWorld

from woke.fuzzer.contract import Abi

from pathlib import Path

logging.basicConfig(filename='test.log', level=logging.DEBUG)

def test_hello_world():
    start_time = time.time()
    #hello: HelloWorld = HelloWorld.deploy()
    hello = HelloWorld.deploy(666)
    #print(hello.counter())
    counter_val = 0
    for _ in range(100):
        counter_val = hello.incrementCounter()
        hello.helloWorld()
        #out = hello.helloWorld()
    total_time = time.time() - start_time

    path = Path("./output.txt")
    if path.exists():
        with path.open('a') as f:
            f.write(f"total time: {total_time}, counter: {counter_val}\n")
    else:
        path.touch()
        path.write_text(f"total time: {total_time}\n")


def test_fallback():
    hello = HelloWorld.deploy(0)
    data = Abi.encode([50, "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"], ['uint256', 'address'])
    output_data = hello.fallback(data) 
    
    print(f"output of fallback: {Abi.decode(output_data, ['uint256', 'address'])}")
    #hello.helloWorld(request_type='default')
    print(hello.counter())
    print(hello.addr())


#test_hello_world()
test_fallback()

#def test(*args):
#    print(args)
#
#pes = [1, 2, 3]
#test(pes)

#from woke.fuzzer.primitive_types import uint16
#from woke.fuzzer.primitive_types import uint256
#
#from multipledispatch import dispatch
#
#@dispatch(uint16)
#def test(x: uint16):
#    print("16")
#
#@dispatch(uint256)
#def test(x: uint256):
#    print("256")


#class Test():
#    @overload
#    def process(self, response: None) -> None:
#        ...
#    @overload
#    def process(self, response: int) -> int:
#        ...
#    @overload
#    def process(self, response: bytes) -> str:
#        ...
#    def process(self, response):
#        print("test")
#
#test = Test()
#test2 = test.process()
