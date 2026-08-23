"""Simulation Registry Service (Phase 4I.5).

Pre-registers educational topic simulation definitions that plug into the runtime.
"""

from __future__ import annotations

from app.schemas.simulation_runtime import (
    ParameterType,
    SimulationCheckpoint,
    SimulationDefinition,
    SimulationParameter,
    SimulationStep,
)

SAMPLE_CPU_SIMULATION = SimulationDefinition(
    simulation_id="sim_cpu_fetch_execute",
    topic="CPU Von Neumann Fetch-Execute Cycle",
    category="System Architecture",
    description="Interactive step-by-step simulation of instruction fetch, opcode decode, ALU calculation, and memory write-back.",
    parameters=[
        SimulationParameter(
            parameter_id="clock_frequency_mhz",
            label="Clock Frequency (MHz)",
            data_type=ParameterType.FLOAT,
            default_value=1.0,
            current_value=1.0,
            min_value=0.5,
            max_value=4.0,
            step_size=0.5,
            description="Controls the CPU clock tick frequency.",
        ),
        SimulationParameter(
            parameter_id="register_a_value",
            label="Register A Initial Value",
            data_type=ParameterType.INTEGER,
            default_value=15,
            current_value=15,
            min_value=0,
            max_value=255,
            description="Value loaded into Register A accumulator.",
        ),
        SimulationParameter(
            parameter_id="alu_mode",
            label="ALU Operation Mode",
            data_type=ParameterType.SELECT,
            default_value="ADD",
            current_value="ADD",
            options=["ADD", "SUBTRACT", "AND", "OR"],
            description="Mathematical or boolean logic mode.",
        ),
    ],
    steps=[
        SimulationStep(
            step_id="step_1_pc_fetch",
            step_number=1,
            title="Instruction Fetch",
            description="Program Counter (PC) emits address to RAM. RAM transfers opcode 0x1A over data bus into Instruction Register (IR).",
            active_components=["comp_ram", "comp_cu"],
            state_delta={"PC": "0x0004", "IR": "0x1A (ADD)"},
            visual_highlights=["comp_ram", "comp_cu"],
        ),
        SimulationStep(
            step_id="step_2_cu_decode",
            step_number=2,
            title="Opcode Decode",
            description="Control Unit decodes opcode 0x1A as ADD operation and emits control bus signals to ALU and Register file.",
            active_components=["comp_cu", "comp_registers"],
            state_delta={"ControlSignals": "ENABLE_ALU_ADD"},
            visual_highlights=["comp_cu"],
        ),
        SimulationStep(
            step_id="step_3_alu_execute",
            step_number=3,
            title="ALU Calculation",
            description="ALU reads Register A and Register B operands, performs ADD logic, and updates zero flag status.",
            active_components=["comp_alu", "comp_registers"],
            state_delta={"ALU_Out": "42", "ZeroFlag": False},
            visual_highlights=["comp_alu", "comp_registers"],
        ),
        SimulationStep(
            step_id="step_4_writeback",
            step_number=4,
            title="Result Write-Back",
            description="Result 42 is stored back into Accumulator Register. PC increments to next instruction.",
            active_components=["comp_registers", "comp_ram"],
            state_delta={"Accumulator": "42", "PC": "0x0008"},
            visual_highlights=["comp_registers"],
        ),
    ],
    checkpoints=[
        SimulationCheckpoint(
            checkpoint_id="chk_fetch",
            step_number=1,
            title="Fetch Cycle Understanding",
            explanation="The Program Counter holds the memory address of the next instruction to fetch from RAM.",
            hint="Which component provides the instruction memory address?",
            expected_concept="Program Counter emits address to RAM.",
        ),
        SimulationCheckpoint(
            checkpoint_id="chk_alu",
            step_number=3,
            title="ALU Execution Logic",
            explanation="The ALU computes mathematical and logical results based on Control Unit signals.",
            hint="What signals activate the ALU operation?",
            expected_concept="Control Unit decodes opcode and signals ALU.",
        ),
    ],
    learning_objectives=[
        "Trace PC instruction pointer increments.",
        "Observe opcode decoding in Control Unit.",
        "Verify ALU calculation outputs and register write-back.",
    ],
)

SAMPLE_SORTING_SIMULATION = SimulationDefinition(
    simulation_id="sim_bubble_sort",
    topic="Bubble Sort Algorithm",
    category="Algorithm",
    description="Step-by-step array element comparisons and swaps.",
    parameters=[
        SimulationParameter(
            parameter_id="array_size",
            label="Array Size",
            data_type=ParameterType.INTEGER,
            default_value=5,
            current_value=5,
            min_value=3,
            max_value=10,
        )
    ],
    steps=[
        SimulationStep(
            step_id="sort_step_1",
            step_number=1,
            title="Compare Pair [0, 1]",
            description="Compare element A[0]=5 with A[1]=3. Since 5 > 3, swap elements.",
            active_components=["comp_array_0", "comp_array_1"],
            state_delta={"Array": [3, 5, 8, 1, 2]},
        ),
        SimulationStep(
            step_id="sort_step_2",
            step_number=2,
            title="Compare Pair [1, 2]",
            description="Compare element A[1]=5 with A[2]=8. Since 5 < 8, no swap required.",
            active_components=["comp_array_1", "comp_array_2"],
            state_delta={"Array": [3, 5, 8, 1, 2]},
        ),
    ],
    checkpoints=[
        SimulationCheckpoint(
            checkpoint_id="chk_swap",
            step_number=1,
            title="Swap Condition",
            explanation="Swap adjacent elements when left > right.",
            hint="When is a swap triggered?",
            expected_concept="Left element greater than right.",
        )
    ],
    learning_objectives=["Understand adjacent comparison and bubbling largest element to end."],
)


SAMPLE_PHOTOSYNTHESIS_SIMULATION = SimulationDefinition(
    simulation_id="sim_photosynthesis",
    topic="Photosynthesis Process",
    category="Biology",
    description="Interactive simulation of light-dependent and light-independent reactions in plant chloroplasts.",
    parameters=[
        SimulationParameter(
            parameter_id="light_intensity",
            label="Light Intensity (lux)",
            data_type=ParameterType.FLOAT,
            default_value=500.0,
            current_value=500.0,
            min_value=0.0,
            max_value=1000.0,
            step_size=100.0,
            description="Intensity of light hitting the chloroplast.",
        ),
        SimulationParameter(
            parameter_id="co2_concentration",
            label="CO2 Concentration (%)",
            data_type=ParameterType.FLOAT,
            default_value=0.04,
            current_value=0.04,
            min_value=0.01,
            max_value=0.10,
            step_size=0.01,
            description="Carbon dioxide available for Calvin cycle.",
        ),
    ],
    steps=[
        SimulationStep(
            step_id="photo_step_1",
            step_number=1,
            title="Light Absorption",
            description="Chlorophyll pigments in thylakoid membranes absorb photons, exciting electrons to higher energy states.",
            active_components=["comp_chlorophyll", "comp_thylakoid"],
            state_delta={"ElectronState": "excited", "PhotonEnergy": "captured"},
            visual_highlights=["comp_chlorophyll"],
        ),
        SimulationStep(
            step_id="photo_step_2",
            step_number=2,
            title="Water Splitting (Photolysis)",
            description="Water molecules are split into hydrogen ions, electrons, and oxygen gas by the oxygen-evolving complex.",
            active_components=["comp_water", "comp_thylakoid"],
            state_delta={"H2O": "2H+ + 2e- + O2", "Oxygen": "released"},
            visual_highlights=["comp_water"],
        ),
        SimulationStep(
            step_id="photo_step_3",
            step_number=3,
            title="ATP and NADPH Production",
            description="Electron transport chain generates ATP via chemiosmosis and reduces NADP+ to NADPH.",
            active_components=["comp_electron_transport", "comp_atp_synthase"],
            state_delta={"ATP": "produced", "NADPH": "produced"},
            visual_highlights=["comp_electron_transport"],
        ),
        SimulationStep(
            step_id="photo_step_4",
            step_number=4,
            title="Calvin Cycle (Carbon Fixation)",
            description="RuBisCO fixes CO2 into G3P molecules using ATP and NADPH from light reactions, producing glucose.",
            active_components=["comp_calvin_cycle", "comp_rubisco"],
            state_delta={"CO2": "fixed", "G3P": "produced", "Glucose": "synthesized"},
            visual_highlights=["comp_calvin_cycle"],
        ),
    ],
    checkpoints=[
        SimulationCheckpoint(
            checkpoint_id="chk_light",
            step_number=1,
            title="Light Reaction Purpose",
            explanation="Light reactions convert solar energy into chemical energy (ATP and NADPH).",
            hint="What energy carriers are produced in the thylakoid?",
            expected_concept="ATP and NADPH store energy from photons.",
        ),
        SimulationCheckpoint(
            checkpoint_id="chk_calvin",
            step_number=4,
            title="Carbon Fixation",
            explanation="The Calvin cycle uses ATP and NADPH to convert CO2 into organic sugar molecules.",
            hint="Which enzyme captures CO2 from the atmosphere?",
            expected_concept="RuBisCO catalyzes carbon fixation.",
        ),
    ],
    learning_objectives=[
        "Trace the flow of energy from sunlight to chemical bonds in glucose.",
        "Understand the role of water as an electron donor in photolysis.",
        "Explain how the Calvin cycle produces sugar from CO2.",
    ],
)

SAMPLE_WATER_CYCLE_SIMULATION = SimulationDefinition(
    simulation_id="sim_water_cycle",
    topic="Water Cycle",
    category="Earth Science",
    description="Simulation of evaporation, condensation, precipitation, and collection in the hydrological cycle.",
    parameters=[
        SimulationParameter(
            parameter_id="temperature_celsius",
            label="Surface Temperature (C)",
            data_type=ParameterType.FLOAT,
            default_value=25.0,
            current_value=25.0,
            min_value=0.0,
            max_value=50.0,
            step_size=5.0,
            description="Surface temperature driving evaporation rate.",
        ),
        SimulationParameter(
            parameter_id="humidity_percent",
            label="Atmospheric Humidity (%)",
            data_type=ParameterType.FLOAT,
            default_value=60.0,
            current_value=60.0,
            min_value=10.0,
            max_value=100.0,
            step_size=10.0,
            description="Current humidity level affecting condensation threshold.",
        ),
    ],
    steps=[
        SimulationStep(
            step_id="water_step_1",
            step_number=1,
            title="Evaporation",
            description="Solar energy heats surface water bodies, causing water molecules to gain kinetic energy and escape into the atmosphere as water vapor.",
            active_components=["comp_ocean", "comp_sun"],
            state_delta={"WaterState": "liquid->gas", "Altitude": "rising"},
            visual_highlights=["comp_ocean"],
        ),
        SimulationStep(
            step_id="water_step_2",
            step_number=2,
            title="Condensation",
            description="Rising water vapor cools at higher altitudes, condensing around dust particles to form tiny water droplets and clouds.",
            active_components=["comp_clouds", "comp_atmosphere"],
            state_delta={"WaterState": "gas->liquid", "CloudFormation": "active"},
            visual_highlights=["comp_clouds"],
        ),
        SimulationStep(
            step_id="water_step_3",
            step_number=3,
            title="Precipitation",
            description="When cloud droplets merge and become too heavy, they fall as rain, snow, sleet, or hail depending on temperature.",
            active_components=["comp_clouds", "comp_land"],
            state_delta={"Rainfall": "active", "CloudMass": "depleting"},
            visual_highlights=["comp_clouds", "comp_land"],
        ),
        SimulationStep(
            step_id="water_step_4",
            step_number=4,
            title="Collection and Runoff",
            description="Precipitation collects in rivers, lakes, and oceans. Some infiltrates groundwater. The cycle repeats.",
            active_components=["comp_river", "comp_ocean", "comp_groundwater"],
            state_delta={"WaterLevel": "restored", "CyclePhase": "restart"},
            visual_highlights=["comp_river"],
        ),
    ],
    checkpoints=[
        SimulationCheckpoint(
            checkpoint_id="chk_evap",
            step_number=1,
            title="Evaporation Energy Source",
            explanation="The sun provides the thermal energy that drives evaporation of surface water.",
            hint="What provides the energy to change water from liquid to gas?",
            expected_concept="Solar radiation provides kinetic energy for evaporation.",
        ),
        SimulationCheckpoint(
            checkpoint_id="chk_condense",
            step_number=2,
            title="Cloud Formation",
            explanation="Condensation occurs when water vapor cools and changes back to liquid droplets around condensation nuclei.",
            hint="What triggers water vapor to change back to liquid?",
            expected_concept="Cooling at altitude causes phase change from gas to liquid.",
        ),
    ],
    learning_objectives=[
        "Trace the complete path of a water molecule through all four cycle stages.",
        "Understand energy transfers driving phase changes at each stage.",
        "Explain how evaporation, condensation, and precipitation are interconnected.",
    ],
)

SAMPLE_CELL_DIVISION_SIMULATION = SimulationDefinition(
    simulation_id="sim_cell_division",
    topic="Cell Division Mitosis",
    category="Biology",
    description="Step-by-step simulation of mitotic cell division from prophase through cytokinesis.",
    parameters=[
        SimulationParameter(
            parameter_id="chromosome_count",
            label="Initial Chromosome Count",
            data_type=ParameterType.INTEGER,
            default_value=46,
            current_value=46,
            min_value=4,
            max_value=46,
            step_size=2,
            description="Number of chromosomes in the parent cell.",
        ),
    ],
    steps=[
        SimulationStep(
            step_id="mitosis_step_1",
            step_number=1,
            title="Prophase — Chromosome Condensation",
            description="Chromatin condenses into visible chromosomes. The nuclear envelope begins to break down. Centrioles migrate to opposite poles.",
            active_components=["comp_chromatin", "comp_centrioles"],
            state_delta={"ChromatinState": "condensed", "NuclearEnvelope": "dissolving"},
            visual_highlights=["comp_chromatin"],
        ),
        SimulationStep(
            step_id="mitosis_step_2",
            step_number=2,
            title="Metaphase — Chromosome Alignment",
            description="Spindle fibers attach to kinetochores. Chromosomes align along the metaphase plate (cell equator).",
            active_components=["comp_spindle", "comp_chromosomes"],
            state_delta={"Alignment": "metaphase_plate", "SpindleAttachment": "complete"},
            visual_highlights=["comp_spindle"],
        ),
        SimulationStep(
            step_id="mitosis_step_3",
            step_number=3,
            title="Anaphase — Sister Chromatid Separation",
            description="Cohesin proteins are cleaved. Sister chromatids are pulled apart by shortening spindle fibers toward opposite poles.",
            active_components=["comp_spindle", "comp_chromatids"],
            state_delta={"ChromatidsSeparated": True, "CellElongation": "active"},
            visual_highlights=["comp_spindle"],
        ),
        SimulationStep(
            step_id="mitosis_step_4",
            step_number=4,
            title="Telophase and Cytokinesis",
            description="Nuclear envelopes reform around each set of chromosomes. The cytoplasm divides (cytokinesis), producing two identical daughter cells.",
            active_components=["comp_nuclearEnvelope", "comp_cleavage_furrow"],
            state_delta={"DaughterCells": 2, "DivisionComplete": True},
            visual_highlights=["comp_cleavage_furrow"],
        ),
    ],
    checkpoints=[
        SimulationCheckpoint(
            checkpoint_id="chk_metaphase",
            step_number=2,
            title="Chromosome Alignment",
            explanation="Metaphase ensures each daughter cell will receive one copy of each chromosome.",
            hint="Why must chromosomes align at the center before separation?",
            expected_concept="Equatorial alignment ensures equal distribution.",
        ),
        SimulationCheckpoint(
            checkpoint_id="chk_anaphase",
            step_number=3,
            title="Separation Mechanism",
            explanation="Spindle fibers shorten and pull sister chromatids to opposite poles, ensuring genetic consistency.",
            hint="What molecular event triggers chromatid separation?",
            expected_concept="Cohesin cleavage allows chromatid separation.",
        ),
    ],
    learning_objectives=[
        "Identify each phase of mitosis by chromosome behavior.",
        "Understand how spindle fibers ensure equal chromosome distribution.",
        "Explain why mitosis produces genetically identical daughter cells.",
    ],
)


class SimulationRegistryService:

    def __init__(self) -> None:
        self._registry: dict[str, SimulationDefinition] = {
            SAMPLE_CPU_SIMULATION.simulation_id: SAMPLE_CPU_SIMULATION,
            SAMPLE_SORTING_SIMULATION.simulation_id: SAMPLE_SORTING_SIMULATION,
            SAMPLE_PHOTOSYNTHESIS_SIMULATION.simulation_id: SAMPLE_PHOTOSYNTHESIS_SIMULATION,
            SAMPLE_WATER_CYCLE_SIMULATION.simulation_id: SAMPLE_WATER_CYCLE_SIMULATION,
            SAMPLE_CELL_DIVISION_SIMULATION.simulation_id: SAMPLE_CELL_DIVISION_SIMULATION,
        }

    def register_simulation(self, definition: SimulationDefinition) -> None:
        self._registry[definition.simulation_id] = definition

    def get_simulation(self, simulation_id: str) -> SimulationDefinition | None:
        return self._registry.get(simulation_id)

    def list_simulations(self, category: str | None = None) -> list[SimulationDefinition]:
        defs = list(self._registry.values())
        if category:
            return [d for d in defs if d.category.lower() == category.lower()]
        return defs


simulation_registry = SimulationRegistryService()
