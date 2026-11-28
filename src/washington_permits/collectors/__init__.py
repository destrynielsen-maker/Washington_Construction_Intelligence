from .seattle import SeattleCollector
from .grant_county import GrantCountyCollector
from .kennewick import KennewickCollector
from .moses_lake import MosesLakeCollector
from .yakima_county import YakimaCountyCollector

COLLECTORS = [SeattleCollector(), KennewickCollector(), YakimaCountyCollector(), MosesLakeCollector(), GrantCountyCollector()]
