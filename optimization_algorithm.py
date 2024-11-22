import gurobipy as gp
from gurobipy import GRB
import pandas as pd
import tabulate
import plotly.figure_factory as ff

# Quelle:
# https://tidel.mie.utoronto.ca/pubs/JSP_CandOR_2016.pdf
# Genutzt wird das time indexed Modell

machines = [0, 1, 2, 3, 4, 5, 6]
machine_designations = {0: "EXAPT-CAM 1",   #CAM Vorbereitung
                        1: "EXAPT-CAM 2",   #CAM Vorbereitung
                        2: "WEISSER - ARTERY",  #Drehen + Fräsen
                        3: "DMG-MORI - CTX Beta 800 V4",    #Drehen
                        4: "MAZAK - CV 500",    #Drehen + Fräsen
                        5: "DMG-MORI - DMU 65", #Fräsen
                        6: "HELLER - HF 3500"}  #Fräsen
machine_energy_consumption = {0: 100,
                              1: 10,
                              2: 100,
                              3: 10,
                              4: 10,
                              5: 10,
                              6: 10}

technologies = [0, 1, 2]
technology_designations = {0: "CAM Vorbereitung", 1: "Drehen", 2: "Fräsen"}
technology_allocation = {0: [0, 1],
                         1: [2, 3, 4],
                        #  1: [2, 3],
                         2: [2, 4, 5, 6]}
                        #  2: [2, 4]}


jobs = [0, 1, 2, 3, 4, 5, 6]
job_designations = {0:"Prod0", 1:"Prod1", 2:"Prod2", 3:"Prod3", 4:"Prod4", 5:"Prod5", 6:"Prod6"}
job_process_order = {0: {0: 1, 1: 3, 2: 3},    # Job 0 muss für eine Zeiteinheit an Technologie 0, dann für drei Zeiteinheiten an Technologie 1,...
                  1: {1: 3, 2: 3},
                  2: {0: 3, 2: 3},
                  3: {1: 1, 2: 3, 2: 5},
                  4: {0: 1, 2: 3},
                  5: {1: 1, 2: 4},
                  6: {0: 6, 2: 6, 1: 6}}
job_quantity = {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 1, 6: 1}
# jobs = [0, 1, 2]  # Jobs
# machines = [0, 1, 2]      # Maschinen
# processing_time = {  # Bearbeitungszeiten p_ij [job][maschine]
#     (0, 0): 3, (0, 1): 4, (0, 2): 1,
#     (1, 0): 5, (1, 1): 2, (1, 2): 2,
#     (2, 0): 2, (2, 1): 6, (2, 2): 0
# }
time_period = range(100)

# Initialisiere das Modell
model = gp.Model("JobScheduling")


# # Setze PoolSearchMode auf 2, um mehrere Lösungen zu finden
# model.setParam(GRB.Param.PoolSearchMode, 2)

# # Setze die maximale Anzahl von Lösungen, die im Pool gespeichert werden sollen
# model.setParam(GRB.Param.PoolSolutions, 10)

# Variablen: Startzeiten x_ij
x = model.addVars(jobs, machines, technologies, time_period, vtype=GRB.BINARY, name="x")

# Cmax Variable (für makespan)
Cmax = model.addVar(vtype=GRB.INTEGER, name="Cmax")
Jmax = model.addVar(vtype=GRB.INTEGER, name="Jmax")
energy_consumed = model.addVar(vtype=GRB.INTEGER, name="energy_consumed")
# penalty = model.addVar(vtype=GRB.INTEGER, name="penalty")

# Variable k: Ganze Zahl, gibt wieder wie oft ein Produktionsschritt erledigt wurde
# k = model.addVars(jobs, machines, vtype=GRB.INTEGER, name="k")
# for j in jobs:
#     for m in machines:
#         model.addConstr(k[j, m] >= 1)

# (1) Jeder Job startet nur einmal auf einer Maschine
for j in jobs: 
     for tech in job_process_order[j].keys():
        # model.addConstr((gp.quicksum(x[j, m, tech, t] for m in technology_allocation[tech] for t in time_period) >= job_quantity[j]), name=f"assign_{j}_{tech}")
        model.addConstr((gp.quicksum(x[j, m, tech, t] for m in technology_allocation[tech] for t in time_period) == 1), name=f"assign_{j}_{tech}")
        # for m in technology_allocation[tech]:
        #     model.addConstr((gp.quicksum(x[j, m, tech, t] for t in time_period) >= job_quantity[j]), name=f"assign_{j}_{tech}")

# (2) Maschine kann zur gleichen Zeit nur einen Job bearbeiten
for m in machines:
    for t in time_period:
        # Summiere alle Jobs, die diese Maschine zum Zeitpunkt t nutzen könnten
        model.addConstr(
            (
                gp.quicksum(
                    x[j, m, tech, t_prime]
                    for j in jobs
                    for tech, duration in job_process_order[j].items()
                    if m in technology_allocation[tech]  # Prüft, ob Maschine für die Technologie verfügbar ist
                    for t_prime in range(max(0, t - (duration*job_quantity[j]) + 1), t + 1)
                )
            ) <= 1,
            name=f"conflict_{m}_{t}"
        )

# (3) Maschinenfolge der Jobs einhalten
for j in jobs:
    # Iteriere über die Prozesse (Technologien) in der Reihenfolge ihrer Bearbeitung
    process_steps = list(job_process_order[j].items())
    
    for idx in range(1, len(process_steps)):
        # Aktueller und vorheriger Prozessschritt (Technologie und Dauer)
        tech_prev, duration_prev = process_steps[idx - 1]
        tech_curr, duration_curr = process_steps[idx]
        
        # Maschinen, die der aktuellen und vorherigen Technologie zugeordnet sind
        machines_prev = technology_allocation[tech_prev]
        machines_curr = technology_allocation[tech_curr]
        
        model.addConstr(
                    (
                        gp.quicksum((t + (duration_prev*job_quantity[j])) * x[j, m_prev, tech_prev, t]  for m_prev in machines_prev for t in time_period) 
                        <= gp.quicksum(t * x[j, m_curr, tech_curr, t]  for m_curr in machines_curr for t in time_period)
                    ),
                    name=f"Sequence. Job: {j}; tech_jetzt:{tech_curr}"
                )

#         # Erstellen der Nebenbedingungen für die Maschinenfolge
        # for m_prev in machines_prev:
        #     for m_curr in machines_curr:
        #         model.addConstr(
        #             (
        #                 gp.quicksum((t + duration_prev - 1) * x[j, m_prev, tech_prev, t]  for t in time_period) 
        #                 <= gp.quicksum(t * x[j, m_curr, tech_curr, t] - 1 for t in time_period)
        #             ),
        #             name=f"Sequence. Job: {j}; m_vorher:{m_prev}; tech_vorher:{tech_prev}; m_jetzt{m_curr}; tech_jetzt:{tech_curr}"
        #         )

# penalty = gp.quicksum(x[j, m, tech, t] for j in jobs for tech in job_process_order[j].keys() for m in technology_allocation[tech] for t in time_period)

# (5) Letzter Job an einer Maschine darf nicht später starten als die benötigte Produktionsdauer.
# for j in jobs:
#     for tech, duration in job_process_order[j].items():
#         for m in technology_allocation[tech]:
#             model.addConstr(
#                 gp.quicksum(x[j, m, tech, t] for t in range(len(time_period) - duration + 1, len(time_period))) == 0,
#                 name=f"latest_start_{j}_{m}"
#             )

# (7) Bearbeitungsdauer soll min. so lang sein wie der letzte Prozessschritt mit der längsten Prozessdauer
# Nur für Cmax relevant
for j in jobs:
    for tech, duration in job_process_order[j].items():
        for m in technology_allocation[tech]:
            model.addConstr(
                (gp.quicksum((t + (duration*job_quantity[j])) * x[j, m, tech, t] for t in time_period)) <= Cmax, 
                name=f"cmax_{j}_{m}"
            )

# Gesamte Dauer die benötigt wird um alle Schritte in einem Job zu erledigen
# for j in jobs: 
#     model.addConstr(
#                 (gp.quicksum((t + (duration*job_quantity[j])) * x[j, m, tech, t] for tech, duration in job_process_order[j].items() for m in technology_allocation[tech] for t in time_period)) <= Jmax, 
#                 name=f"jmax_{j}_{m}"
#             )
# for j in jobs: 
#     for tech, duration in job_process_order[j].items():
#         model.addConstr(
#                     (gp.quicksum((t + (duration*job_quantity[j])) * x[j, m, tech, t] for m in technology_allocation[tech] for t in time_period)) <= Jmax, 
#                     name=f"jmax_{j}_{m}"
#                 )

# Wenn Summe über alles gebildet wird, dann werden die Jobs so schnell wie möglich erledigt, aber die Gesamtdauer alle Jobs zu erledigen steigt. 
# Im Vergleich zu der Herangehensweise eins drüber
Jmax = gp.quicksum((t + (duration*job_quantity[j])) * x[j, m, tech, t] for j in jobs for tech, duration in job_process_order[j].items() for m in technology_allocation[tech] for t in time_period)

# switch_amount = gp.quicksum(x[j, m, tech, t] for j in jobs for m in machines for tech in technologies for t in time_period)

energy_consumed = gp.quicksum(x[j, m, tech, t]*machine_energy_consumption[m] for j in jobs for tech in job_process_order[j] for m in technology_allocation[tech] for t in time_period)

# model.setObjective(Cmax, GRB.MINIMIZE)
# model.setObjective(Cmax + energy_consumed, GRB.MINIMIZE)
# model.setObjective(energy_consumed, GRB.MINIMIZE)
model.setObjective(Cmax + energy_consumed + Jmax, GRB.MINIMIZE) 
# model.setObjective(Cmax + energy_consumed + 1000*penalty, GRB.MINIMIZE)
# model.setObjective(Cmax + energy_consumed + 10*switch_amount, GRB.MINIMIZE)
# model.setObjective(Cmax + switch_amount, GRB.MINIMIZE)

model.Params.TimeLimit = 60

# Optimierung durchführen
model.optimize()

# Wenn das Modell unlösbar ist, fordere das IIS an
if model.status == GRB.INFEASIBLE:
    print("Das Modell ist unlösbar. Berechne IIS...")
    model.computeIIS()  # Berechnet das IIS (Irreducible Inconsistent Subsystem)
    model.write("infeasible.ilp")  # Speichert die IIS-Beschränkungen in einer Datei
    
    # Ausgabe der unlösbaren Constraints
    print("\nDie folgenden Constraints sind Teil des IIS (Irreducible Inconsistent Subsystem):")
    for c in model.getConstrs():
        if c.IISConstr:
            print(f"{c.constrName}")
else:
    # Falls eine optimale Lösung gefunden wurde
    # if model.status == GRB.OPTIMAL:

        # print(f"Strafe: {penalty}")
    
        table_data = []
    
        for j in jobs:
            for tech, duration in job_process_order[j].items():
                for m in technology_allocation[tech]:
                    for t in time_period:
                        if x[j, m, tech, t].X > 0.5:
                            start_time = t
                            end_time = t + duration  
                            machine_name = machine_designations[m]
                            tech_name = technology_designations[tech]
                            
                            # Daten für die Tabelle
                            table_data.append([f"Job {j}", machine_name, tech_name, start_time, end_time])
                            

        # Ergebnis-Tabelle speichern und anzeigen
        print(tabulate.tabulate(table_data, headers=["Job", "Machine", "Technology", "Start", "End"], tablefmt="grid"))
    

        # for m in machines:
            
        #     # Tabellentitel: Zeitperioden als Spalten
        #     headers = ["Job \\ Zeit"] + [f"T{t}" for t in time_period]

        #     # Liste für die Tabellendaten
        #     table = []

        #     # Durchlaufe alle Jobs und fülle die Tabelle
        #     for j in jobs:
        #         # Zeilenkopf: Job-Name
        #         row = [f"Job {job_designations[j]}"]
        #         for tech in job_process_order.keys():
        #             for t in time_period:
        #                 if x[j, m, tech, t].X > 0.5:  # Wenn die Startzeit für diesen Job in dieser Zeitperiode ist
        #                     row.append(1)  # Job läuft in dieser Zeitperiode
        #                 else:
        #                     row.append(0)  # Job läuft nicht in dieser Zeitperiode
        #             table.append(row)
            
        #     # Ausgabe der Tabelle mit tabulate
        #     # print(tabulate.tabulate(table, headers, tablefmt="grid"))
        #     with open(machine_designations[m], 'w') as f:
        #         f.write(tabulate.tabulate(table, headers, tablefmt="grid"))
        
        data_for_gantt = []

        # # Iteriere über alle Jobs und Technologien
        for j in jobs:
            for tech, duration in job_process_order[j].items():  # Für jede Technologie und ihre Dauer im Job
                # Maschinenliste für die aktuelle Technologie abrufen
                machines_for_tech = technology_allocation[tech]
                
                for t in time_period:
                    # Gehe über die Maschinen, die dieser Technologie zugeordnet sind
                    for m in machines_for_tech:
                        # Prüfen, ob die Variable x[j, m, t] den Wert 1 hat (Job j startet auf Maschine m bei Zeit t)
                        if x[j, m, tech, t].X > 0.5:
                            # Aufgabe für das Gantt-Diagramm erstellen
                            task = {
                                "Task": f"{machine_designations[m]}",
                                "Start": t,
                                "Finish": t + duration*job_quantity[j],
                                # "Resource": f"{job_designations[j]} - {technology_designations[tech]}"
                                "Resource": f"{job_designations[j]}"
                            }
                            data_for_gantt.append(task)

        # DataFrame zur Darstellung im Gantt-Diagramm erstellen
        df = pd.DataFrame(data=data_for_gantt, columns=["Task", "Start", "Finish", "Resource"])

        # Gantt-Diagramm erstellen
        fig = ff.create_gantt(df, index_col='Resource', bar_width=0.4, show_colorbar=True, group_tasks=True, showgrid_x=True)
        fig.update_layout(xaxis_type='linear')
        fig.update_traces(mode='lines', line_color='black', selector=dict(fill='toself'))
        fig.show()

"""
Modell 2 nicht benötigt da alles in Modell 1 abgedeckt ist.
"""

# machines_2 = []

# for m in machines:
#     j = 0
#     for i in x.select("*", m, "*", "*"):
#         if i.X == 1: 
#             j = 1
#             machines_2.append(m)
#     if j == 0:
#         for tech in technologies:
#             if m in technology_allocation[tech]:
#                 technology_allocation[tech].remove(m)

# # print(machines_2)
# print(f"technology_allocation: {technology_allocation}")

# job_process_order_machine_based = {}

# # for j in jobs: 
# #     job_process_order_machine_based[j] = {}
# #     for tech, duration in job_process_order[j].items():
# #         for m in technology_allocation[tech]:
# #             tmp_dict = {}
# #             for i in x.select(j, m, tech, "*"):
# #                 if i.X == 1: 
# #                     # print(f"j: {j}, m: {m}, tech: {tech}")
# #                     tmp_dict[m] = duration
# #                     # job_process_order_machine_based[j][m] += duration
# #             if len(tmp_dict) != 0:
# #                 machine_keys = job_process_order_machine_based[j].keys()
# #                 if m not in machine_keys:
# #                     job_process_order_machine_based[j].update(tmp_dict)
# #                 else:
# #                     job_process_order_machine_based[j][m] += duration

# for j in jobs: 
#     job_process_order_machine_based[j] = {}
#     for tech, duration in job_process_order[j].items():
#         job_process_order_machine_based[j][tech] = {}
#         for m in technology_allocation[tech]:
#             tmp_dict = {}
#             for i in x.select(j, m, tech, "*"):
#                 if i.X == 1: 
#                     # print(f"j: {j}, m: {m}, tech: {tech}")
#                     tmp_dict[m] = duration
#                     # job_process_order_machine_based[j][m] += duration
#             if len(tmp_dict) != 0:
#                 machine_keys = job_process_order_machine_based[j][tech].keys()
#                 if m not in machine_keys:
#                     job_process_order_machine_based[j][tech].update(tmp_dict)
#                 else:
#                     job_process_order_machine_based[j][tech][m] += duration

# print(f"job_process_order_machine_based: {job_process_order_machine_based}")

# model_2 = gp.Model("JobScheduling2")

# x_2 = model_2.addVars(jobs, machines, time_period, vtype=GRB.BINARY, name="x_2")
# Cmax_2 = model_2.addVar(vtype=GRB.INTEGER, name="Cmax_2")

# # (1) Jeder Job startet nur einmal auf einer Maschine
# for j in jobs:
#     for tech in job_process_order_machine_based[j].keys():
#         for m in job_process_order_machine_based[j][tech].keys():
#             model_2.addConstr((gp.quicksum(x_2[j, m, t] for t in time_period) == 1), name=f"assign_{j}_{m}")

# # (2) Maschine kann zur gleichen Zeit nur einen Job bearbeiten
# # for j in jobs: 
# #     for m, duration in job_process_order_machine_based[j].items():
# #         for t in time_period:
# #             model_2.addConstr((gp.quicksum(x_2[j, m, t_prime] for t_prime in range(max(0, t - duration + 1), t + 1)))<= 1, name=f"conflict_{m}_{t}")

# # for j in jobs:
# #     for m in machines_2:
# #         if m in job_process_order_machine_based[j].keys():
# #             for t in time_period:
# #                 # print(f"t: {t}, m: {m}, j: {j}")
# #                 # print(job_process_order_machine_based[j][m])
# #                 model_2.addConstr((gp.quicksum(x_2[j, m, t_prime] for t_prime in range(max(0, t - job_process_order_machine_based[j][m] + 1), t + 1)))<= 1, name=f"conflict_{m}_{t}")

# for m in machines_2:
#     for t in time_period:
#         # print(f"t: {t}, m: {m}, j: {j}")
#         # print(job_process_order_machine_based[j][m])
#         model_2.addConstr((gp.quicksum(x_2[j, m, t_prime] for j in jobs for tech in job_process_order_machine_based[j] if m in job_process_order_machine_based[j][tech].keys() for t_prime in range(max(0, t - job_process_order_machine_based[j][tech][m] + 1), t + 1)))<= 1, name=f"conflict_{m}_{t}")


# # (3) Maschinenfolge der Jobs einhalten. 
# for j in jobs: 
#     tech_process_steps = list(job_process_order_machine_based[j].keys())
#     for idx in range(1, len(tech_process_steps)):
#         tech_curr = tech_process_steps[idx]
#         tech_prev = tech_process_steps[idx-1]

#         curr = list(job_process_order_machine_based[j][tech_curr].keys())
#         prev = list(job_process_order_machine_based[j][tech_prev].keys())

#         m_curr = curr[0]
#         m_prev = prev[0]
#         model_2.addConstr((gp.quicksum((t + job_process_order_machine_based[j][tech_prev][m_prev])*x_2[j, m_prev, t] -1 for t in time_period) <= gp.quicksum(t*x_2[j, m_curr, t] - 1 for t in time_period)), name=f"sequence_{j}_{t}")

# # (7) Bearbeitungsdauer soll min. so lang sein wie der letzte Prozessschritt mit der längsten Prozessdauer
# # Nur für Cmax relevant
# for j in jobs:
#     for tech in list(job_process_order_machine_based[j].keys()):
#         for m, duration in job_process_order_machine_based[j][tech].items():
#             model_2.addConstr((gp.quicksum((t + duration)*x_2[j, m, t] for t in time_period)) <= Cmax_2, name=f"cmax_{j}_{m}")

# model_2.setObjective(Cmax_2, GRB.MINIMIZE)

# model_2.optimize()

# if model_2.status == GRB.INFEASIBLE:
#     print("Das Modell ist unlösbar. Berechne IIS...")
#     model_2.computeIIS()  # Berechnet das IIS (Irreducible Inconsistent Subsystem)
#     model_2.write("infeasible.ilp")  # Speichert die IIS-Beschränkungen in einer Datei
    
#     # Ausgabe der unlösbaren Constraints
#     print("\nDie folgenden Constraints sind Teil des IIS (Irreducible Inconsistent Subsystem):")
#     for c in model_2.getConstrs():
#         if c.IISConstr:
#             print(f"{c.constrName}")
# else:
#     # Falls eine optimale Lösung gefunden wurde
#     if model_2.status == GRB.OPTIMAL:

#         table_data = []
    
#         for j in jobs:
#             for tech in job_process_order_machine_based[j].keys():
#                 for m, duration in job_process_order_machine_based[j][tech].items():
#                     for t in time_period:
#                         if x_2[j, m, t].X > 0.5:
#                             start_time = t
#                             end_time = t + duration  
#                             machine_name = machine_designations[m]
#                             tech_name = technology_designations[tech]
                            
#                             # Daten für die Tabelle
#                             table_data.append([f"Job {j}", machine_name, tech_name, start_time, end_time])
                            

#         # Ergebnis-Tabelle speichern und anzeigen
#         print(tabulate.tabulate(table_data, headers=["Job", "Machine", "Technology", "Start", "End"], tablefmt="grid"))
 

#         for m in machines_2:
#             # print(f"\nMaschine {machine_designations[m]}:")
            
#             # Tabellentitel: Zeitperioden als Spalten
#             headers = ["Job \\ Zeit"] + [f"T{t}" for t in time_period]

#             # Liste für die Tabellendaten
#             table = []

#             # Durchlaufe alle Jobs und fülle die Tabelle
#             for j in jobs:
#                 # Zeilenkopf: Job-Name
#                 row = [f"Job {job_designations[j]}"]
#                 # Werte in den Zellen: Variable x[j, m, t]
#                 for t in time_period:
#                     if x_2[j, m, t].X > 0.5:  # Wenn die Startzeit für diesen Job in dieser Zeitperiode ist
#                         row.append(1)  # Job läuft in dieser Zeitperiode
#                     else:
#                         row.append(0)  # Job läuft nicht in dieser Zeitperiode
#                 table.append(row)
            
#             # Ausgabe der Tabelle mit tabulate
#             # print(tabulate.tabulate(table, headers, tablefmt="grid"))
#             with open(machine_designations[m], 'w') as f:
#                 f.write(tabulate.tabulate(table, headers, tablefmt="grid"))

#         data_y_machines = []
#         for j in jobs:
#             for tech in job_process_order_machine_based[j].keys():
#                 for m in job_process_order_machine_based[j][tech].keys():
#                     for t in time_period:
#                         for e in x_2.select(j, m, t):
#                             if e.X == 1:
#                                 task = dict(Task=machine_designations[m], Start=t, Finish=t+(job_process_order_machine_based[j][tech][m]), Resource=job_designations[j])
#                                 data_y_machines.append(task)

#         df = pd.DataFrame(data=data_y_machines, columns = ["Task", "Start", "Finish", "Resource"])

#         fig = ff.create_gantt(df, index_col = 'Resource',  bar_width = 0.4, show_colorbar=True, group_tasks=True, showgrid_x=True)
#         fig.update_layout(xaxis_type='linear')
#         fig.update_traces(mode='lines', line_color='black', selector=dict(fill='toself'))
#         fig.show()
