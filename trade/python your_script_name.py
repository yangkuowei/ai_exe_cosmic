import matplotlib.pyplot as plt
import ast # 用于安全地解析字符串形式的字典

# 1. 将你的训练日志数据粘贴到这个多行字符串中
log_data_string = """
{'loss': 2.4805, 'grad_norm': 0.4173945188522339, 'learning_rate': 3.6363636363636364e-05, 'epoch': 0.09}
{'loss': 2.3922, 'grad_norm': 0.31769561767578125, 'learning_rate': 8.181818181818183e-05, 'epoch': 0.19}
{'loss': 2.1953, 'grad_norm': 0.40812236070632935, 'learning_rate': 9.677419354838711e-05, 'epoch': 0.28}
{'loss': 2.0909, 'grad_norm': 0.29029399156570435, 'learning_rate': 9.13978494623656e-05, 'epoch': 0.38}
{'loss': 2.0159, 'grad_norm': 0.268396258354187, 'learning_rate': 8.60215053763441e-05, 'epoch': 0.47}
{'loss': 1.9354, 'grad_norm': 0.27263060212135315, 'learning_rate': 8.064516129032258e-05, 'epoch': 0.57}
{'loss': 1.8302, 'grad_norm': 0.26969027519226074, 'learning_rate': 7.526881720430108e-05, 'epoch': 0.66}
{'loss': 1.7812, 'grad_norm': 0.2912265360355377, 'learning_rate': 6.989247311827958e-05, 'epoch': 0.76}
{'loss': 1.7658, 'grad_norm': 0.2996176481246948, 'learning_rate': 6.451612903225807e-05, 'epoch': 0.85}
{'loss': 1.6811, 'grad_norm': 0.3030250072479248, 'learning_rate': 5.913978494623657e-05, 'epoch': 0.95}
{'loss': 2.0411, 'grad_norm': 0.32075756788253784, 'learning_rate': 5.3763440860215054e-05, 'epoch': 1.06}
{'loss': 1.6184, 'grad_norm': 0.3144891858100891, 'learning_rate': 4.8387096774193554e-05, 'epoch': 1.15}
{'loss': 1.5493, 'grad_norm': 0.3287546634674072, 'learning_rate': 4.301075268817205e-05, 'epoch': 1.25}
{'loss': 1.553, 'grad_norm': 0.3637302815914154, 'learning_rate': 3.763440860215054e-05, 'epoch': 1.34}
{'loss': 1.5233, 'grad_norm': 0.35174453258514404, 'learning_rate': 3.2258064516129034e-05, 'epoch': 1.44}
{'loss': 1.5709, 'grad_norm': 0.376897931098938, 'learning_rate': 2.6881720430107527e-05, 'epoch': 1.53}
{'loss': 1.5462, 'grad_norm': 0.3624393939971924, 'learning_rate': 2.1505376344086024e-05, 'epoch': 1.62}
"""

# 2. 解析数据
data = []
for line in log_data_string.strip().split('\n'):
    try:
        # 使用 ast.literal_eval 安全地将字符串转换为字典
        data_point = ast.literal_eval(line)
        data.append(data_point)
    except (ValueError, SyntaxError) as e:
        print(f"警告：跳过无法解析的行: {line} - 错误: {e}")

# 3. 提取用于绘图的数据列
epochs = [item['epoch'] for item in data]
losses = [item['loss'] for item in data]
grad_norms = [item['grad_norm'] for item in data]
learning_rates = [item['learning_rate'] for item in data]

# 4. 创建可视化图表
# 创建一个图形和三个子图 (共享 x 轴)
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 12), sharex=True)
fig.suptitle('Training Metrics Over Epochs', fontsize=16) # 总标题

# 子图 1: 训练损失 (Loss)
ax1.plot(epochs, losses, marker='o', linestyle='-', color='tab:blue')
ax1.set_ylabel('Loss')
ax1.set_title('Training Loss')
ax1.grid(True)

# 子图 2: 梯度范数 (Gradient Norm)
ax2.plot(epochs, grad_norms, marker='o', linestyle='-', color='tab:orange')
ax2.set_ylabel('Gradient Norm')
ax2.set_title('Gradient Norm')
ax2.grid(True)

# 子图 3: 学习率 (Learning Rate)
ax3.plot(epochs, learning_rates, marker='o', linestyle='-', color='tab:green')
ax3.set_ylabel('Learning Rate')
ax3.set_title('Learning Rate')
ax3.set_xlabel('Epoch') # X 轴标签只在最下面的子图显示
ax3.grid(True)
# 为了更好地显示学习率的小数值，可以使用科学计数法
ax3.ticklabel_format(style='sci', axis='y', scilimits=(0,0))

# 调整子图布局，防止标签重叠
plt.tight_layout(rect=[0, 0.03, 1, 0.96]) # 调整布局以适应总标题

# 显示图表
plt.show()

print("\n图表已生成并显示。")
