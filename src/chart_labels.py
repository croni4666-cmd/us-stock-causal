"""Bilingual display labels; source symbols, units and numeric metadata stay intact."""
import matplotlib as mpl
from matplotlib import font_manager


def configure_chart_font():
    available={font.name for font in font_manager.fontManager.ttflist}
    candidates=('Microsoft YaHei','Noto Sans CJK SC','Noto Sans CJK JP','SimHei',
                'WenQuanYi Zen Hei','Arial Unicode MS')
    selected=[name for name in candidates if name in available]
    mpl.rcParams['font.family']='sans-serif'
    mpl.rcParams['font.sans-serif']=selected+['DejaVu Sans']
    mpl.rcParams['axes.unicode_minus']=False


def unit_label(unit):
    translations={'USD/oz':'美元/盎司','USD/share':'美元/份','USD':'美元',
        'index points':'指数点','VIX points':'波动率指数点','bp':'基点',
        '%':'百分比','provider quote units':'数据源报价单位'}
    return unit+'（'+translations[unit]+'）' if unit in translations else unit


def instrument_label(symbol):
    translations={'GC=F':'COMEX黄金期货','GLD':'黄金ETF','QQQ':'纳斯达克100 ETF',
        '^IXIC':'纳斯达克综合指数','IEF':'7—10年美债ETF','TLT':'20年以上美债ETF',
        '^VIX':'波动率指数','^TNX':'10年美债收益率','DXY':'美元指数',
        'DIA':'道琼斯30 ETF','RSP':'标普500等权ETF','QQQE':'纳斯达克100等权ETF',
        'XLB':'材料','XLC':'通信服务','XLE':'能源','XLF':'金融','XLI':'工业',
        'XLK':'信息技术','XLP':'必需消费','XLRE':'房地产','XLU':'公用事业',
        'XLV':'医疗保健','XLY':'可选消费'}
    return symbol+'（'+translations[symbol]+'）' if symbol in translations else symbol
