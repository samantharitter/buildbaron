
## Requirements

Requires Python 3.5

## To do analysis of build failures

Install

```
pip3 install -r www/requirements.txt
```

It is a two step process:

1. Do the analysis

```
python3 evg_analyzer.py
```

2. View the analysis

```
python3 www\runserver.py
```
The webserver is running at <http://localhost:5555/>

## Other Useful Scripts

*Scripts to deduplicate stacks from hang_analyzer.py*

```
python3 win_deadlock_analyzer.py
python3 gdb_deadlock_analyzer.py
```
