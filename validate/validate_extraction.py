import json
import math
from typing import Tuple

MAX_WORKLOAD = 50


def validate_extrac(self, json_str: str) -> Tuple[bool, str]:
    """
    验证JSON格式并检查每个功能点的工作量不超过50
    工作量 = (cosmic_total_lines*workload_percentage)/100 向上取整
    """
    try:
        data = json.loads(json_str)
        cosmic_total_lines = data.get('cosmic_total_lines', 0)

        if not data.get('solution_details'):
            return True, ''

        for detail in data['solution_details']:
            percentage = detail.get('workload_percentage', 0)
            workload = math.ceil((cosmic_total_lines * percentage) / 100)
            if workload > 50:
                return False, f'功能点"{detail["feature_point"]}"的工作量{workload}超过50'

        return True, ''
    except json.JSONDecodeError:
        return False, '无效的JSON格式'
    except Exception as e:
        return False, f'验证失败: {str(e)}'
