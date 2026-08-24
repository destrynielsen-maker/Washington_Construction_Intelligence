from pathlib import Path
from .pipeline import run

if __name__ == "__main__":
    result=run(Path(__file__).resolve().parents[2])
    print(result)
