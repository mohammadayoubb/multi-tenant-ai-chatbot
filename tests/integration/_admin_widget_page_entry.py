# Owner: Amer
"""Test-only Streamlit entrypoint that runs admin/widget_page.render().

AppTest.from_function extracts a function's source as a script and loses
access to the page module's `import streamlit as st`. Using AppTest.from_file
on this two-line wrapper avoids that pitfall while still exercising the real
render() implementation.
"""
from admin.widget_page import render

render()
