import gurobipy as gp
from gurobipy import GRB
import pandas as pd
import tabulate
import plotly.figure_factory as ff

machines = [0, 1, 2, 3, 4, 5, 6]
machine_designations = {0: "EXAPT-CAM 1",   #CAM Vorbereitung
                        1: "EXAPT-CAM 2",   #CAM Vorbereitung
                        2: "WEISSER - ARTERY",  #Drehen + Fräsen
                        3: "DMG-MORI - CTX Beta 800 V4",    #Drehen
                        4: "MAZAK - CV 500",    #Drehen + Fräsen
                        5: "DMG-MORI - DMU 65", #Fräsen
                        6: "HELLER - HF 3500"}  #Fräsen
machine_energy_consumption = {0: 10,
                              1: 10,
                              2: 10,
                              3: 10,
                              4: 10,
                              5: 10,
                              6: 10}

technologies = [0, 1, 2]
technology_designations = {0: "CAM Vorbereitung", 1: "Drehen", 2: "Fräsen"}
technology_allocation = {0: [0, 1],
                         1: [2, 3, 4],
                         2: [2, 4, 5, 6]}


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
time_period = range(100)

model = gp.Model("JobScheduling")

# # Setze PoolSearchMode auf 2, um mehrere Lösungen zu finden
# model.setParam(GRB.Param.PoolSearchMode, 2)

# # Setze die maximale Anzahl von Lösungen, die im Pool gespeichert werden sollen
# model.setParam(GRB.Param.PoolSolutions, 10)

# Variable: Startzeiten x_j,m,tech,t
x = model.addVars(jobs, machines, technologies, time_period, vtype=GRB.BINARY, name="x")

# Variable: Gesamtproduktionsdauer Cmax
Cmax = model.addVar(vtype=GRB.INTEGER, name="Cmax")

# Variable: Produktionsdauer für einen Job Jmax
Jmax = model.addVar(vtype=GRB.INTEGER, name="Jmax")

# Variable: Gesamter Energieverbrauch energy_consumed
energy_consumed = model.addVar(vtype=GRB.INTEGER, name="energy_consumed")


# (1) Jeder Job startet für eine Technologie nur einmal auf einer Maschine.
# Mehrfachstart auf einer Maschine möglich, wenn jedes mal unterschiedliche Technologien der Maschine genutzt werden.
for j in jobs: 
     for tech in job_process_order[j].keys():
        model.addConstr((gp.quicksum(x[j, m, tech, t] for m in technology_allocation[tech] for t in time_period) == 1), name=f"assign_{j}_{tech}")

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

# (4) Bearbeitungsdauer soll min. so lang sein wie der letzte Prozessschritt mit der längsten Prozessdauer
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

# (5) 
# Wenn Summe über alles gebildet wird, dann werden die Jobs so schnell wie möglich erledigt, aber die Gesamtdauer alle Jobs zu erledigen steigt. 
# Im Vergleich zu der Herangehensweise eins drüber
Jmax = gp.quicksum((t + (duration*job_quantity[j])) * x[j, m, tech, t] for j in jobs for tech, duration in job_process_order[j].items() for m in technology_allocation[tech] for t in time_period)

# (6) Summe der von den Maschinen verbrauchten Energie
energy_consumed = gp.quicksum(x[j, m, tech, t]*machine_energy_consumption[m]*duration for j in jobs for tech, duration in job_process_order[j].items() for m in technology_allocation[tech] for t in time_period)

model.setObjective(Cmax + energy_consumed + Jmax, GRB.MINIMIZE) 

# Maximale Rechendauer in Sekunden
# model.Params.TimeLimit = 60

# Optimierung durchführen
model.optimize()

# Wenn das Modell unlösbar ist, fordere das IIS (Irreducible Inconsistent Subsystem) an
if model.status == GRB.INFEASIBLE:
    print("Das Modell ist unlösbar. Berechne IIS...")
    model.computeIIS()  
    model.write("infeasible.ilp")  
    
    # Ausgabe der unlösbaren Constraints
    print("\nDie folgenden Constraints sind Teil des IIS (Irreducible Inconsistent Subsystem):")
    for c in model.getConstrs():
        if c.IISConstr:
            print(f"{c.constrName}")
else:
    # Falls eine optimale Lösung gefunden wurde
    if model.status == GRB.OPTIMAL:

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
                            

        # Ergebnistabelle speichern und anzeigen
        print(tabulate.tabulate(table_data, headers=["Job", "Machine", "Technology", "Start", "End"], tablefmt="grid"))
    
        data_for_gantt = []

        for j in jobs:
            for tech, duration in job_process_order[j].items():
                machines_for_tech = technology_allocation[tech]
                
                for t in time_period:
                    for m in machines_for_tech:
                        if x[j, m, tech, t].X > 0.5:
                            task = {
                                "Task": f"{machine_designations[m]}",
                                "Start": t,
                                "Finish": t + duration*job_quantity[j],
                                # "Resource": f"{job_designations[j]} - {technology_designations[tech]}"
                                "Resource": f"{job_designations[j]}"
                            }
                            data_for_gantt.append(task)

        df = pd.DataFrame(data=data_for_gantt, columns=["Task", "Start", "Finish", "Resource"])

        # Gantt-Diagramm erstellen
        fig = ff.create_gantt(df, index_col='Resource', bar_width=0.4, show_colorbar=True, group_tasks=True, showgrid_x=True)
        fig.update_layout(xaxis_type='linear')
        fig.update_traces(mode='lines', line_color='black', selector=dict(fill='toself'))
        fig.show()