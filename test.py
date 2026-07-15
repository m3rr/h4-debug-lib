import urllib.request
import time
import os

print("Starting test script...")
time.sleep(1)

print("Making a network request...")
try:
    response = urllib.request.urlopen("http://httpbin.org/get")
    print("Response code:", response.getcode())
except Exception as e:
    print("Network request failed:", e)

print("Writing to a file...")
with open("test_output.txt", "w") as f:
    f.write("Hello from h4-debug test!\n")

print("Reading from file...")
with open("test_output.txt", "r") as f:
    print(f.read().strip())

print("Doing some execution tracing...")
def a():
    b()

def b():
    c()

def c():
    print("In C")

a()

print("Test script finished!")
