# LOSReader 3.0.0

This is a helper program for reading letters of support.

## Prerequisites
Install [Python](https://www.python.org/). Make sure the box that adds Python to PATH is checked.

## Installation
[Download](https://docs.github.com/en/get-started/start-your-journey/downloading-files-from-github) the files and unzip to your preferred location.

Open your terminal (Windows: PowerShell/Command Prompt, macOS: Terminal)

1. Navigate to the folder
```bash
cd path/to/project
```
2. Install dependencies

```bash
pip install -r requirements.txt
```

## Usage
Files are stored in three main folders: **samples, results, and cache.**

+ samples - Save the letters to this folder. The program can handle PDF and image files. 
+ results - This is where the output files are stored in PDF format.
+ cache - This is where the raw text extracted from the original file is stored.

Periodically clear out these folders.
