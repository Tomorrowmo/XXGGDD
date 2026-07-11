"""
控制箱和实验室数据处理
"""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from A00_parameterData import headerIndex
from A00_parameterData import headerIndex, S_position, S_index


k = 1.4  # 气体常数
A_isoIn = 0.06*0.5   # 隔离段入口面积

delta_time = 0.02032  # 控制箱和试验台压力时间差

print("数据文件时间差 = {} 秒".format("%.8f" % delta_time))



# ----------------------------------------------------------------------------------------------------------------------
"""运行log文件分析"""
fileName_log = "/home/gaoyi/python_proj/20240513-01-Ma6-control/resourceData/A7C_log_runTime_2024513165159.csv"

dataAll_huidu = pd.read_csv(fileName_log, encoding="gbk")

time_huidu = np.asarray(dataAll_huidu.iloc[:, 1])
time_40 = np.asarray(dataAll_huidu.iloc[:, 1])

time_cost = np.asarray(dataAll_huidu.iloc[:, 2])  # 运算耗时

p_loacl = np.asarray(dataAll_huidu.iloc[:, 3])  # 燃烧室当前室压

Inj_1 = np.asarray(dataAll_huidu.iloc[:, 29])  # 喷1控制信号
Inj_2 = np.asarray(dataAll_huidu.iloc[:, 30])  # 喷2控制信号

AI8_40 = np.asarray(dataAll_huidu.iloc[:, 4])  # AI8-40采样率
AI9_40 = np.asarray(dataAll_huidu.iloc[:, 5])  # AI9-40采样率
AI10_40 = np.asarray(dataAll_huidu.iloc[:, 6])  # AI10-40采样率
AI11_40 = np.asarray(dataAll_huidu.iloc[:, 7])  # AI11-40采样率

AI8_ave = np.asarray(dataAll_huidu.iloc[:, 32])  # AI8-平均
AI9_ave = np.asarray(dataAll_huidu.iloc[:, 33])  # AI9-平均
AI10_ave = np.asarray(dataAll_huidu.iloc[:, 34])  # AI10-平均
AI11_ave = np.asarray(dataAll_huidu.iloc[:, 35])  # AI11-平均

AI29_40 = np.asarray(dataAll_huidu.iloc[:, 22])  # AI29


# ----------------------------------------------------------------------------------------------------------------------
"""测试数据"""
fileName = "/home/gaoyi/python_proj/20240513-01-Ma6-control/resourceData/控制箱测试数据-20240513-02-Ma6.txt"

dataAll = []
dataAll_1 = []
dataAll_2 = []
dataAll_3 = []
dataAll_4 = []
dataAll_5 = []
dataAll_6 = []

AI4_2K = []

AI8_2K = []
AI9_2K = []
AI10_2K = []
AI11_2K = []


AI24_2K = []
AI27_2K = []
AI28_2K = []
AI29_2K = []


with open(fileName, "r") as f:
    for row in f:
        AI4_2K.append(row.split()[4])
        dataAll.append(row.split()[4])

        dataAll_1.append(row.split()[8])

        AI8_2K.append(row.split()[8])
        AI9_2K.append(row.split()[9])
        AI10_2K.append(row.split()[10])
        AI11_2K.append(row.split()[11])

        dataAll_2.append(row.split()[9])
        dataAll_3.append(row.split()[10])
        dataAll_4.append(row.split()[11])
        dataAll_5.append(row.split()[12])
        dataAll_6.append(row.split()[13])

        AI24_2K.append(row.split()[24])
        AI27_2K.append(row.split()[27])
        AI28_2K.append(row.split()[28])
        AI29_2K.append(row.split()[29])


dataAll_new = np.asarray(dataAll[1:], dtype=float)  # 触发
time = np.arange(0, len(dataAll_new)/2000, 1/2000)   # 时间

# 时间
time_2K = np.arange(0, len(dataAll_new)/2000, 1/2000)

#  触发信号 2K
AI4_2K = np.asarray(AI4_2K[1:], dtype=np.float64)

"""光电信号处理"""
AI8_2K = np.asarray(AI8_2K[1:], dtype=np.float64)  # AI8 - 光电
AI8_2K = AI8_2K-AI8_2K[0]

AI9_2K = np.asarray(AI9_2K[1:], dtype=np.float64)  # AI9 - 光电
AI9_2K = AI9_2K-AI9_2K[0]

AI10_2K = np.asarray(AI10_2K[1:], dtype=np.float64)  # AI10 - 光电
AI10_2K = AI10_2K-AI10_2K[0]

AI11_2K = np.asarray(AI11_2K[1:], dtype=np.float64)  # AI11 - 光电
AI11_2K = AI11_2K-AI11_2K[0]

dataAll_new1 = np.asarray(dataAll_1[1:], dtype=float)  # AI8 - 光电
dataAll_new1 = dataAll_new1-dataAll_new1[0]
#
dataAll_new2 = np.asarray(dataAll_2[1:], dtype=float)  # AI9 - 光电
dataAll_new2 = dataAll_new2-dataAll_new2[0]

dataAll_new3 = np.asarray(dataAll_3[1:], dtype=float)  # AI10
# dataAll_new3 = dataAll_new3*0.275-0.375+0.101325

dataAll_new4 = np.asarray(dataAll_4[1:], dtype=float)  # AI11 - 燃烧室压力47
dataAll_new4 = dataAll_new4*0.275-0.375+0.101325

dataAll_new5 = np.asarray(dataAll_5[1:], dtype=float)  # AI12
# dataAll_new5 = dataAll_new5*0.275-0.375+0.101325

PP_48 = np.asarray(dataAll_5[1:], dtype=float)  # AI12 - 燃烧室压力48
PP_48 = PP_48*0.275-0.375+0.101325

PP_50 = np.asarray(dataAll_6[1:], dtype=float)  # AI13 - 燃烧室压力50
PP_50 = PP_50*0.275-0.375+0.101325

"""----------------------------------------控制箱测试-隔离段测点---------------------------------------------------------"""

AI24_2K = np.asarray(AI24_2K[1:], dtype=float)  # AI24 - 隔离段下侧测点
AI24_2K = AI24_2K*0.275-0.375+0.101325

AI27_2K = np.asarray(AI27_2K[1:], dtype=float)  # AI27 - 隔离段下侧测点
AI27_2K = AI27_2K*0.275-0.375+0.101325


"""----------------------------------------控制箱测试-燃烧室测点---------------------------------------------------------"""

AI28_2K = np.asarray(AI28_2K[1:], dtype=float)  # AI28 - 一级凹腔燃烧室压力
AI28_2K = AI28_2K*0.275-0.375+0.101325

AI29_2K = np.asarray(AI29_2K[1:], dtype=float)  # AI29 - 一级凹腔燃烧室压力
AI29_2K = AI29_2K*0.275-0.375+0.101325

# 光电信号滤波
AI8_filter = []

# print(np.sort(np.asarray([3, 6, 1, 5, 9])))

for i in range(len(dataAll_new1)):
    if 0 <= i <= 24:
        AI8_filter.append(dataAll_new1[i])
    else:
        # AI8_filter.append(np.average(dataAll_new1[i-25:i]))
        AI8_filter.append(np.sort(dataAll_new1[i-25:i])[12])
# print(AI8_filter)


########################################################################################################################
"""实验室数据处理"""
def visual_fileData(fileName):
    dataAll = []
    with open(fileName, "r", encoding="utf-8") as f:
        for row in f:
            dataAll.append(row)

    file_header = dataAll[headerIndex]

    dataAll_new = []
    for i in range(len(dataAll)):
        if i > headerIndex:
            dataAll_new.append(dataAll[i].split(","))
        else:
            pass

    dataAll_newFloat = np.zeros(shape=np.shape(dataAll_new))

    for i in range(len(dataAll_new)):
        for j in range(len(dataAll_new[0])):
            dataAll_newFloat[i, j] = float(dataAll_new[i][j])

    return file_header, dataAll_newFloat


# """试验台测试数据"""
file_ST_1 = "/home/gaoyi/python_proj/20240513-01-Ma6-control/resourceData/20240513-A7C-Ma6-3kg-第五十七车-热试-隔离段.txt"
header_ST_1, dataAll_ST_1 = visual_fileData(file_ST_1)
print("文件1名称 = ", file_ST_1)
print("文件1头文件 = ", header_ST_1.split(","))
print("文件1数据大小 = ", np.shape(dataAll_ST_1))
index_1 = 26
print("列索引 = {}，头名称 = {}".format(index_1, header_ST_1.split(",")[index_1]))
print("列索引 = {}，头名称 = {}".format(25, header_ST_1.split(",")[25]))


file_ST_2 = "/home/gaoyi/python_proj/20240513-01-Ma6-control/resourceData/20240513-A7C-Ma6-3kg-第五十七车-热试-流道.txt"
header_ST_2, dataAll_ST_2 = visual_fileData(file_ST_2)
print("文件2名称 = ", file_ST_2)
print("文件2头文件 = ", header_ST_2.split(","))
print("文件2数据大小 = ", np.shape(dataAll_ST_2))
index_2 = 1
print("列索引 = {}，头名称 = {}".format(index_2, header_ST_2.split(",")[index_2]))


'''文件1'''
print("--------------------------------文件1数据索引检查--------------------------------")

# Time-ST1
index_time_ST1 = 0
time_ST1 = np.asarray(dataAll_ST_1[:, index_time_ST1])
print("索引编号={}   --->   名称={}".format(index_time_ST1, header_ST_1.split(",")[index_time_ST1]))

# 喷1喷前
index_Inj_p1 = 30
Inj_p1 = np.asarray(dataAll_ST_1[:, index_Inj_p1]+0.101325)
print("索引编号={}   --->   名称={}".format(index_Inj_p1, header_ST_1.split(",")[index_Inj_p1]))

# 喷2喷前
index_Inj_p2 = 32
Inj_p2 = np.asarray(dataAll_ST_1[:, index_Inj_p2]+0.101325)
print("索引编号={}   --->   名称={}".format(index_Inj_p2, header_ST_1.split(",")[index_Inj_p2]))

# 甲烷火箭室压
index_CH4_p = 36
p_CH4 = np.asarray(dataAll_ST_1[:, index_CH4_p]+0.101325)
print("索引编号={}   --->   名称={}".format(index_CH4_p, header_ST_1.split(",")[index_CH4_p]))


# 确定索引
index_pTotal = 25  # 总压，传感器编号1
p_total = np.asarray(dataAll_ST_2[:, index_pTotal]+0.101325)

# Time
index_time = 0
time_ST = np.asarray(dataAll_ST_2[:, index_time])
print("索引编号={}   --->   名称={}".format(index_time, header_ST_2.split(",")[index_time]))

# 流道15
index_P_15 = 47
P_15 = np.asarray(dataAll_ST_2[:, index_P_15]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_15, header_ST_2.split(",")[index_P_15]))

# 流道18
index_P_18 = 50
P_18 = np.asarray(dataAll_ST_2[:, index_P_18]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_18, header_ST_2.split(",")[index_P_18]))

# 流道22
index_P_22 = 54
P_22 = np.asarray(dataAll_ST_2[:, index_P_22]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_22, header_ST_2.split(",")[index_P_22]))

# 流道23
index_P_23 = 55
P_23 = np.asarray(dataAll_ST_2[:, index_P_23]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_23, header_ST_2.split(",")[index_P_23]))

# 流道26
index_P_26 = 58
P_26 = np.asarray(dataAll_ST_2[:, index_P_26]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_26, header_ST_2.split(",")[index_P_26]))

# 流道29
index_P_29 = 61
P_29 = np.asarray(dataAll_ST_2[:, index_P_29]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_29, header_ST_2.split(",")[index_P_29]))

# 流道30
index_P_30 = 62
P_30 = np.asarray(dataAll_ST_2[:, index_P_30]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_30, header_ST_2.split(",")[index_P_30]))

# 流道34
index_P_34 = 66
P_34 = np.asarray(dataAll_ST_2[:, index_P_34]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_34, header_ST_2.split(",")[index_P_34]))

# 流道35
index_P_35 = 67
P_35 = np.asarray(dataAll_ST_2[:, index_P_35]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_35, header_ST_2.split(",")[index_P_35]))

# 流道38
index_P_38 = 70
P_38 = np.asarray(dataAll_ST_2[:, index_P_38]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_38, header_ST_2.split(",")[index_P_38]))

# 流道39
index_P_39 = 71
P_39 = np.asarray(dataAll_ST_2[:, index_P_39]+0.101325)
print("索引编号={}   --->   名称={}".format(index_P_39, header_ST_2.split(",")[index_P_39]))

P_test_01 = np.asarray(dataAll_ST_2[:, 57]+0.101325)
print("索引编号={}   --->   名称={}".format(57, header_ST_2.split(",")[57]))


########################################################################################################################
"""高速相机拍摄结果处理对比"""
file_flame_1 = "/home/gaoyi/python_proj/20240513-01-Ma6-control/flame_visual/data/test-2024_06_02_14_51_39.csv"
data_flame_1 = pd.read_csv(file_flame_1, encoding="gbk")

index_f1 = np.asarray(data_flame_1.iloc[:, 0])

value_f1 = np.asarray(data_flame_1.iloc[:, 1])
value_f1 = (value_f1-np.min(value_f1))/(np.max(value_f1)-np.min(value_f1))
value_f1 = np.asarray(value_f1)

zone100_f1 = np.asarray(data_flame_1.iloc[:, 2])
zone100_f1 = (zone100_f1-np.min(zone100_f1))/(np.max(zone100_f1)-np.min(zone100_f1))
zone100_f1 = np.asarray(zone100_f1)

num_f1 = np.shape(index_f1)[0]

print("f1文件数据数量 = {}\n".format(num_f1))
time_f1 = np.arange(0, num_f1/8000, 1/8000)+2.4-0.017
print(value_f1)




# 主流道沿流向传感器数据提取
print("传感器总数 = ", np.shape(S_index))

time_ST_2 = time_ST

matrix_allSensor = []
for i in range(len(S_index)):
    matrix_allSensor.append(np.asarray(dataAll_ST_2[:, S_index[i]]+0.101325))
matrix_allSensor = np.asarray(matrix_allSensor, dtype=np.float64).T

print("文件2时间向量数据大小 = ", np.shape(time_ST_2))
print("流道所有时刻所有压力的压力数据矩阵大小 = ", np.shape(matrix_allSensor))

# 时间索引计算
index_single = 8759
print("索引={}  --->  时间={}s".format(index_single, time_ST_2[index_single]+delta_time))









########################################################################################################################
"""数据可视化"""
labelSize = 38

########################################################################################################################
"""AI29 AI29、比例阀控制信号、喷前压力"""
plt.figure(figsize=(14, 8))
# plt.rcParams['axes.unicode_minus'] = False
# plt.rcParams["font.family"] = "serif"
# plt.rcParams["font.serif"] = ["Times New Roman"]+plt.rcParams["font.serif"]
plt.rcParams['font.family'] = 'STIX Two Text'
plt.rcParams['mathtext.fontset'] = 'stix'  # 数学公式也用 stix
plt.rcParams['axes.unicode_minus'] = False  # 负号正常显示
plt.rcParams['xtick.direction'] = 'in'
plt.rcParams['ytick.direction'] = 'in'
plt.rcParams["xtick.major.size"] = 10
plt.rcParams["ytick.major.size"] = 10
plt.rcParams["xtick.major.width"] = 2
plt.rcParams["ytick.major.width"] = 2
plt.rcParams["xtick.minor.visible"] = True
plt.rcParams["ytick.minor.visible"] = True
plt.rcParams["xtick.minor.size"] = 5
plt.rcParams["ytick.minor.size"] = 5
plt.rcParams["xtick.minor.width"] = 1.5
plt.rcParams["ytick.minor.width"] = 1.5
plt.rcParams["axes.linewidth"] = 2

plt.xlim(0, 16)
plt.xlabel("Time, s", fontsize=labelSize-6, fontweight="bold")
plt.xticks(fontsize=labelSize-6)

# plt.ylim(-0.01, 0.25)
plt.ylabel("p, MPa", fontsize=labelSize-6, fontweight="bold")
plt.yticks(fontsize=labelSize-6)

# 试验台测试
plt.plot(time_ST+delta_time, P_23, label="First_S1", color="black", linestyle="-", linewidth=2)
plt.plot(time_ST+delta_time, P_29, label="First_S2", color="blue", linestyle="-", linewidth=2)
plt.plot(time_ST+delta_time, P_30, label="Second_S3", color="green", linestyle="-", linewidth=2)
plt.plot(time_ST+delta_time, P_34, label="Second_S4", color="orange", linestyle="-", linewidth=2)

plt.plot(time_ST+delta_time, P_test_01, label="error_test", color="red", linestyle="-", linewidth=2)

# plt.plot(time_ST+delta_time, P_39, label="P39_2K", color="orange", linestyle="-", linewidth=1.5)  # 流道39
# plt.plot(time_ST+delta_time, P_34, label="P34_2K", color="cyan", linestyle="-", linewidth=1.5)  # 流道39

# plt.plot(time_2K+0.025*2, AI29_2K, label="AI29_2K", color="gray", linestyle="-", linewidth=1.5)
# plt.plot(time_40, AI29_40, label="AI29_40", color="blue", linestyle="-", linewidth=3, marker="o")

plt.legend(fontsize=labelSize-8, handletextpad=0.10, loc="upper center", frameon=False, ncol=1)
plt.tight_layout()


plt.twinx()  # ---------------------------------------------------------------------------------------------------------

plt.ylim(-0.024, 0.6)
plt.ylabel("Equivalence ratio", fontsize=labelSize-6, fontweight="bold")
plt.yticks(fontsize=labelSize-6)

# plt.plot(time_40, Inj_1, label="Inj-1", color="brown", linestyle="-", linewidth=3, marker="o")
# plt.plot(time_40, Inj_2, label="Inj-2", color="green", linestyle="-", linewidth=3, marker="^")

m_C10H22 = -8.9156*Inj_p1**4+58.301*Inj_p1**3-139.28*Inj_p1**2+187.02*Inj_p1+10.733
m_C10H22 = m_C10H22/1000
ER_1 = m_C10H22/142*15.5*32/0.232/3.0

# time_sss = np.arange(4.0, 7.0, 0.001)
# V_sss = -0.517*time_sss+3.62
# m_sss = (51.636*V_sss**4-347.68*V_sss**3+852.58*V_sss**2-784.26*V_sss**1+265.98)/1000
# ER_sss = m_sss/142*15.5*32/0.232/3.0


plt.plot(time_ST1+delta_time, ER_1, label="Injector_1", color="red", linestyle="-", linewidth=3.0)

# plt.plot(time_sss, ER_sss, label="Injector_1_cal", color="cyan", linestyle="-", linewidth=3.0)

# plt.plot(time_ST1+delta_time, Inj_p2, label="Inj-P2", color="blue", linestyle="-", linewidth=1.5)

plt.legend(fontsize=labelSize-8, handletextpad=0.10, loc="upper right", frameon=False, ncol=1)
plt.tight_layout()

plt.savefig("./results_png/blow.png", format="png", dpi=100, bbox_inches='tight')




# ---------------------------------------------------------------------------------------------------------------------- #
"""熄火过程流道压力分布曲线"""

plt.figure(figsize=(14, 8))

plt.xlim(0.0, 2.85)
plt.xlabel("X, m", fontsize=labelSize-6, fontweight="bold")
plt.xticks(fontsize=labelSize-6)
#
plt.ylim(-0.01, 0.25)
plt.ylabel("p, MPa", fontsize=labelSize-6, fontweight="bold")
plt.yticks(np.arange(0, 0.30, 0.05), fontsize=labelSize-6)

# 试验台测试
plt.plot(S_position, matrix_allSensor[7959, :], label="t=4.00s", color="red", linestyle="-", linewidth=3, marker="o", markersize=10)

plt.plot(S_position, matrix_allSensor[8759, :], label="t=4.40s", color="blue", linestyle="--", linewidth=3, marker="^", markersize=10)
plt.plot(S_position, matrix_allSensor[9319, :], label="t=4.68s", color="orange", linestyle="--", linewidth=3, marker="v", markersize=10)
plt.plot(S_position, matrix_allSensor[9879, :], label="t=4.96s", color="green", linestyle="--", linewidth=3, marker="<", markersize=10)
plt.plot(S_position, matrix_allSensor[11199, :], label="t=5.62s", color="brown", linestyle="--", linewidth=3, marker=">", markersize=10)
plt.plot(S_position, matrix_allSensor[11999, :], label="t=6.02s", color="cyan", linestyle="--", linewidth=3, marker="D", markersize=10)
plt.plot(S_position, matrix_allSensor[13559, :], label="t=6.80s", color="black", linestyle="-", linewidth=3, marker="s", markersize=10)
plt.plot(S_position, matrix_allSensor[14359, :], label="t=7.20s", color="pink", linestyle="-", linewidth=3, marker="d", markersize=10)

plt.legend(fontsize=labelSize-8, handletextpad=0.10, loc="upper left", frameon=False, ncol=2)
# plt.legend(fontsize=labelSize-8, handletextpad=0.10, loc=(0.00, 0.73), frameon=False, ncol=3)
plt.tight_layout()

plt.savefig("./results_png/流道压力-01.png", format="png", dpi=100, bbox_inches='tight')