/* =============================================================================
   Universal Synthesizer Agent App — Main JS
   Plain vanilla JS, no build step required.
   ============================================================================= */

// ─── Sample JSON (pre-loaded) ──────────────────────────────────────────────────
const SAMPLE_JSON = {
  "request_id": "REQ-SALES-SYNTH-001",
  "app_context": {
    "application_name": "Universal Synthesizer Agent App",
    "agent_name": "Domain Synthesizer Agent",
    "model": "gemma-4-26b-a4b-it",
    "domain": "Sales",
    "objective": "Synthesize structured SQL results and unstructured RAG knowledge into one final user-facing response."
  },
  "persona": {
    "role": "Domain Synthesizer Agent",
    "instruction": "You are a domain-aware synthesizer agent. Use the domain, tables, RAG documents, SQL results, and output schema provided in this JSON to produce a comprehensive, accurate, and actionable response. Treat structured SQL data as the source of truth for transactional facts. Use RAG chunks for policy, guidance, and recommendations. Resolve conflicts by preferring structured data."
  },
  "user_query": "Analyse cancellation patterns across product categories and cancellation reasons, then evaluate carrier-wise shipment performance and delivery status distribution. Highlight key trends, flag any policy compliance concerns, and recommend operational improvements.",
  "input_contract": {
    "structured_input_type": "SQL",
    "unstructured_input_type": "Embedding similarity search",
    "structured_tables_allowed": [
      "semantic_layer.sales_cancellation",
      "semantic_layer.sales_shipment"
    ],
    "rag_table": "tracopp.rag_document_chunks",
    "allowed_rag_documents_only": [
      "Sales_Cancellation_KnowledgeBase.pdf",
      "Sales_Shipment_KnowledgeBase.pdf"
    ]
  },
  "structured_inputs": {
    "sql_scripts": [
      {
        "query_id": "SQL_001",
        "label": "Cancellations by Reason",
        "source_table": "semantic_layer.sales_cancellation",
        "sql": "SELECT cancellation_reason, COUNT(*) AS total_cancellations, ROUND(SUM(refund_amount)::numeric, 2) AS total_refund_amount, ROUND(AVG(refund_amount)::numeric, 2) AS avg_refund_amount FROM semantic_layer.sales_cancellation GROUP BY cancellation_reason ORDER BY total_cancellations DESC;"
      },
      {
        "query_id": "SQL_002",
        "label": "Cancellations by Category and Status",
        "source_table": "semantic_layer.sales_cancellation",
        "sql": "SELECT product_category, cancellation_status, COUNT(*) AS count, ROUND(SUM(refund_amount)::numeric, 2) AS total_refund FROM semantic_layer.sales_cancellation GROUP BY product_category, cancellation_status ORDER BY product_category, count DESC;"
      },
      {
        "query_id": "SQL_003",
        "label": "Carrier Performance",
        "source_table": "semantic_layer.sales_shipment",
        "sql": "SELECT carrier_name, COUNT(*) AS total_shipments, SUM(CASE WHEN LOWER(TRIM(on_time_delivery)) IN ('yes','true','1','y') THEN 1 ELSE 0 END) AS on_time_deliveries, ROUND(AVG(CASE WHEN LOWER(TRIM(on_time_delivery)) IN ('yes','true','1','y') THEN 1.0 ELSE 0.0 END) * 100, 1) AS on_time_rate_pct FROM semantic_layer.sales_shipment GROUP BY carrier_name ORDER BY on_time_rate_pct DESC;"
      },
      {
        "query_id": "SQL_004",
        "label": "Delivery Status Distribution",
        "source_table": "semantic_layer.sales_shipment",
        "sql": "SELECT delivery_status, COUNT(*) AS count, ROUND(AVG(customer_rating)::numeric, 2) AS avg_customer_rating FROM semantic_layer.sales_shipment GROUP BY delivery_status ORDER BY count DESC;"
      }
    ]
  },
  "unstructured_inputs": {
    "similarity_search_inputs": [
      {
        "embedding_id": "EMB_001",
        "label": "Cancellation Policy",
        "content": "What are the refund timelines by payment method, which order types are non-cancellable, and what is the escalation process for disputed cancellations?",
        "embedding": [0.013943, -0.047499, -0.022497, -0.027679, 0.023647, 0.01767, 0.039218, -0.041306, -0.007808, -0.04702, -0.028136, 0.000536, -0.047346, -0.030116, 0.014988, 0.004494, -0.027956, 0.008927, 0.030943, -0.04935, 0.030582, 0.019814, -0.015975, -0.034452, 0.045721, -0.016341, -0.040725, -0.040328, 0.034749, 0.010373, 0.030713, 0.022973, 0.003623, 0.047312, -0.012147, 0.005204, 0.03294, 0.011852, 0.036171, 0.007735, 0.020457, -0.045418, -0.02721, -0.021061, -0.042021, -0.026721, -0.0399, -0.022203, 0.013568, -0.013517, -0.012982, -0.029049, -0.023302, 0.043665, 0.014804, 0.010913, -0.032886, 0.022913, -0.03366, -0.012054, 0.048952, 0.014, 0.005695, 0.018461, 0.034285, 0.0276, -0.027095, -0.04679, -0.018455, -0.023226, -0.028902, 0.044291, 0.037637, -0.018532, 0.015544, -0.010437, 0.041455, -0.004115, -0.023512, -0.025337, 0.006137, -0.023726, 0.008459, 0.039782, -0.01006, -0.028068, 0.049754, 0.000953, -0.040909, -0.045288, -0.039035, 0.012745, 0.029208, -0.007784, -0.043647, -0.011838, 0.049612, 0.002911, 0.047108, 0.036078, -0.048852, 0.022072, 0.018171, 0.003697, -0.023317, 0.014096, -0.038845, -0.006523, -0.004628, 0.045382, 0.037585, -0.023661, 5.9e-05, -0.032135, 0.041263, 0.037052, -0.020156, 0.013895, 0.010897, -0.034716, 0.026251, 0.003938, 0.027863, 0.003035, -0.049943, -0.017584, -0.048052, 0.04291, 0.037872, 0.033167, -0.019249, -0.044207, 0.037801, 0.044695, -0.041435, -0.001401, -0.043079, 0.02606, 0.026583, -0.037161, -0.002472, 0.00498, -0.023494, 0.037243, -0.007686, -0.02882, 0.00393, 0.022993, -0.029885, -0.018828, 0.049515, 0.014988, -0.00619, 0.001758, -0.0379, -0.02753, -0.016191, 0.008831, -0.026989, -0.027978, -0.042901, 0.01311, -0.027106, 0.040542, 0.035964, -0.042914, -0.0262, 0.016898, -0.028576, -0.036769, 0.043551, 0.007104, -0.002733, 0.028462, 0.03075, -0.030959, -0.040307, -0.006895, -0.007642, -0.003298, 0.022908, 0.017336, 0.048417, -0.040158, -0.009738, -0.01607, 0.036167, -0.025134, -0.030979, -0.005139, -0.007812, -0.022145, -0.025019, 0.042327, -0.005687, 0.036135, 0.005033, -0.044941, 0.049928, 0.033603, 0.0469, 0.042637, 0.03487, -0.033369, -0.001436, -0.028625, -0.009896, -0.044136, -0.012103, 0.048531, -0.02348, 0.028407, -0.004499, -0.007699, 0.045732, 0.049542, 0.005577, 0.021841, -0.03452, -0.020329, 0.046871, 0.007918, 0.00422, 0.024798, -0.044283, 0.008418, 0.000285, 0.035272, -0.034257, 0.046078, -0.041989, -0.031418, 0.009504, 0.017521, -0.02648, -0.038011, 0.039029, -0.025378, 0.009452, 0.011938, -0.008078, 0.008367, 0.002278, 0.043471, -0.029574, 0.021619, -0.026131, -0.010421, 0.017169, -0.02, -0.018382, 0.025186, -0.042746, -0.004171, 0.049845, 0.04961, -0.042674, -0.028685, -0.02348, 0.043326, 0.038086, 0.037927, -0.013047, -0.034225, 0.033374, 0.020354, 0.011168, 0.048723, 0.015398, -0.049218, 0.03171, -0.020062, 0.016339, 0.043893, -0.036571, -0.038457, -0.039296, 0.005322, -0.022765, 0.010483, 0.021761, -0.02964, 0.013424, -0.023602, -0.001147, 0.040534, 0.03461, -0.04077, -0.007642, -0.022332, -0.049645, 0.027112, 0.013711, -0.023804, 0.024123, 0.005168, -0.007231, -0.049033, -0.042476, 0.038311, 0.040393, 0.004559, 0.03346, 0.008251, -0.035191, -0.037255, -0.019174, 0.039898, 0.029612, 0.03607, 0.039892, -0.028992, -0.025047, -0.039721, 0.028012, 0.038413, -0.009362, 0.012066, -0.034545, 0.042988, 0.036461, 0.047621, 0.031077, 0.038142, -0.047521, 0.023656, -0.016781, 0.043082, 0.030224, 0.036406, 0.031075, -0.023319, 0.028737, -0.03919, 0.037217, 0.035859, -0.027757, 0.031659, -0.00397, -0.019481, 0.029535, -0.02724, -0.047634, -0.030687, -0.017174, 0.036435, 0.046689, -0.022088, 0.014148, -0.010032, 0.048115, 0.003622, 0.043924, -0.038466, 0.04704, -0.032143, 0.046253, -0.023453, -0.03916, -0.006544, 0.022855, -0.018632, 0.010621, 0.001142, -0.01148, 0.007659, -0.024528, 0.020879, -0.049831, 0.042558, 0.003845, 0.021943, 0.024195, 0.017063, -0.013578, -0.043003, 0.016424, -0.01698, -0.018608, 0.034802, 0.021975, -0.019968, -0.019072, -0.009161, -0.00976, -0.020434, -0.037271, -0.007955, 0.044036, 0.017732, 0.040281, 0.011551, -0.019905, 0.004794, -0.049959, -0.021309, -0.007011, 0.007998, 0.015471, -0.003501, -0.005784, -0.02863, -0.002681, 0.040118, 0.029602, -0.033031, -0.04152, 0.001545, 0.013294, -0.016481, 0.031842, 0.025114, 0.01728, -0.027536, -0.030087, -0.047557, -0.025516, -0.002486, 0.034974, -0.042717, -0.008556, 0.012977, -0.030556, 0.019635, -0.000562, -0.025602, 0.015606, -0.049446, 0.025096, 0.027005, -0.039341, -0.007485, -0.032411, 0.045797, 0.001796, -0.044978, -0.02508, 0.034834, -0.004354, 0.030142, 0.016758, 0.048789, 0.009545, 0.045004, 0.039143, 0.011265, 0.021927, 0.000478, 0.033057, 0.004787, 0.039721, 0.024366, -0.002533, -0.024081, -0.025276, 0.013766, 0.026581, 0.00213, 0.012675, -0.02254, -0.042252, -0.021427, -0.022828, -0.018029, 0.004015, -0.036163, -0.026874, 0.019395, 0.020642, -0.043577, -0.00924, 0.004261, -0.008423, -0.029317, -0.007986, 0.040484, 0.008408, 0.019552, 0.035673, 0.026559, -0.011962, -0.04941, -0.014824, 0.025348, 0.035345, 0.045343, -0.008098, 0.024752, 0.004613, 0.010325, -0.027946, -0.028058, -0.006416, -0.047098, -0.016387, 0.017914, -0.009568, -0.033496, -0.003261, -0.037237, 0.012226, -0.047303, -0.010598, 0.006439, -0.04729, 0.014275, -0.03643, -0.00383, -0.044972, -0.01209, -0.028834, -0.017315, 0.026123, -0.012087, 0.025201, 0.033192, -0.024773, -0.041809, -0.048062, 0.003942, 0.049991, -0.015004, 0.015014, 0.028123, 0.015175, 0.025423, 0.044961, -0.030064, -0.047962, -0.034762, -0.037378, 0.016946, 0.006397, -0.028204, 0.019946, 0.02669, -0.033221, 0.010725, 0.024793, -0.038547, 0.03193, 0.046472, -0.03919, -0.047432, -0.018804, 0.017735, 0.045817, -0.010335, 0.021501, -0.0424, 0.019061, 0.012724, -0.03981, 0.027248, 0.035029, 0.010041, -0.037894, 0.048384, 0.028264, -0.01528, -0.007162, -0.012943, 0.000596, -0.015877, 0.034958, 0.032233, -0.039446, 0.046079, 0.013559, 0.032871, 0.020731, -0.006451, 0.02338, 0.046547, -0.022992, 0.03082, 0.003817, -0.00165, -0.006443, 0.023103, -0.02316, 0.035171, 0.033073, -0.041334, 0.038163, -0.025614, -0.003529, 0.011033, -0.012101, -0.04713, 0.035095, -0.031816, -0.028788, 0.029783, -0.015966, 0.038032, 0.020118, -0.022373, -0.048985, 0.044806, -0.041439, 0.022007, -0.001142, 0.025816, 0.019061, 0.01459, -0.000918, 0.029293, -0.040695, -0.02784, 0.019179, -0.019379, 0.008156, -0.002674, 0.003092, -0.00745, 0.024594, -0.016921, 0.020285, -0.022908, -0.02486, -0.037934, -0.030742, -0.038045, 0.003586, 0.026219, -0.031485, -0.028362, -0.00158, 0.022459, 0.047661, 0.002464, -0.0217, -0.039947, -0.030588, -0.027252, -0.032056, -0.048585, 0.003414, -0.022569, 0.047429, 0.005336, 0.019742, -0.037372, 0.036846, -0.000912, 0.037272, 0.007406, -0.00306, -0.005953, -0.031564, -0.044862, 0.044106, -0.002227, 0.032212, -0.009929, -0.042592, 0.012945, -0.044639, -0.03508, 0.006284, -0.019616, 0.049392, -0.038155, 0.026444, 0.010632, 0.029074, -0.027431, 0.002257, -0.004949, -0.005728, 0.036017, 0.049003, -0.019462, 0.012103, 0.010963, 0.024009, 0.044759, -0.029221, -0.028897, 0.016043, -0.034294, -0.032619, -0.042494, -0.049732, -0.00495, 0.009381, -0.020874, -0.026852, 0.020696, 0.020299, -0.004597, 0.018738, 0.042391, 0.028783, 0.012506, 0.016118, 0.043367, -0.007486, 0.004456, 0.014763, 0.040841, 0.032663, -0.042859, -0.033408, -0.019239, 0.024896, 0.006921, -0.021139, -0.037565, 0.018868, 0.019973, 0.044268, 4.7e-05, -0.00062, -0.041956, -0.046014, -0.006797, -0.017768, -0.024963, -0.040867, 0.046191, 0.033596, 0.00752, 0.045079, 0.049957, 0.017228, -0.023049, -0.045977, 0.025627, -0.00295, 0.015151, 0.041607, -0.031851, 0.008533, 0.013478, -0.000827, -0.040876, -0.015204, -0.016669, 0.017013, 0.035773, -0.01702, 0.019367, -0.021178, 0.044519, 0.031357, 0.00501, -0.004517, -0.018548, -0.017673, 0.047018, -0.009582, 0.00146, 0.048812, 0.015766, 0.004259, -0.008675, -0.031242, -0.013822, 0.025644, 0.012541, 0.025999, -0.029644, 0.004922, 0.042767, -0.006188, 0.019825, -0.037857, 0.047315, 0.010887, -0.02607, -0.034162, 0.005084, 0.005225, -0.040679, 0.049226, 0.041293, -0.003855, -0.038253, 0.033214, -0.000162, 0.02166, 0.000887, -0.022658, 0.033472, 0.048024, -0.025627, 0.005127, -0.011641, 0.042187, 0.000824, 0.037933, 0.036403, -0.022375, 0.029001, -0.008506, 0.043425, 0.000774, 0.032055, -0.021716, -0.020144, 0.008694, 0.04989, -0.001036, -0.03514, 0.003858, -0.015488, 0.005192, 0.004343, -0.004466, -0.017822, -0.031135, 0.01975, 0.00718, -0.026644, 0.027554, -0.045635, 0.024471, 0.020523, 0.031141, -0.011392, 0.016369, 0.032075, 0.048082, -0.000467, -0.046298, 0.000229, 0.009018, 0.03697, 0.037419, -0.005969, 0.002595, -0.004307, 0.022244, -0.009002, 0.015478, -0.034564, -0.003051, 0.04692, -0.016144, 0.01927, 0.014984, 0.035177, 0.035234, 0.035934, -0.011999, -0.018334, 0.021872, 0.02594, 0.037238, -0.04641, -0.043158, 0.013116, 0.042093, 0.049743, 0.024677, -0.006603, -0.040156, 0.013375, 0.037258, -0.005632, 0.0194, 0.040342, -0.045401, 0.029614, -0.020663, -0.012516, -0.035443, 0.003117, 0.006593, 0.029252, -0.033002, -0.042103, 0.037084, 0.011971, -0.025917, 0.041283, -0.035688, -0.003885, -0.024602, -0.024467, -0.04906, 0.030463, 0.040121, 0.017761, -0.034202, -0.005827, -0.015443, 0.008757, 0.013894, -0.007569, -0.02499, 0.03453, -0.030078, -0.011531, -0.001679, -0.026279, 0.007192, 0.007481, 0.049269, -0.020477, 0.047794, 0.015823, -0.022552, 0.006593, 0.01858, 0.024467, -0.045096, 0.010641, -0.000327, 0.040416, -0.021381, 0.029886, 0.010706, -0.014768, 0.013662, 0.012089, 0.017776, 0.022093, 0.015918, 0.033834, 0.012825, 0.04034, 0.014634, -0.019107, -0.005918, 0.007957, 0.023236, -0.040987, -0.020489, 0.024748, -0.032436, -0.036784, 0.003941, 0.047149, 0.003085, 0.041349, 0.033047, -0.024303, 0.032469, -0.001815, 0.030649, 0.024656, -0.016128, -0.038483, 0.046289, -0.035924, 0.04665, 0.036014, 0.022422, 0.047994, 0.046727, 0.030459, -0.013422, 0.029068, -0.048608, 0.003657, -0.004521, 0.017283, 0.017234, 0.008456, 0.032242, 0.044029, -0.039165, -0.026618, -0.047498, 0.038423, 0.006141, 0.041526, -0.027863, -0.043678, 0.032386, 0.040939, -0.019781, -0.00917, -0.036022, 0.044626, -0.019564, -0.000738, -0.040281, 0.038726, -0.036434, -0.004636, 0.017049, 0.024314, 0.044597, -0.008087, 0.024227, -0.034548, -0.008512, -0.040098, -0.001065, -0.009188, 0.045152, -0.046728, -0.012947, -0.005662, 0.045056, 0.035545, -0.040065, 0.018568, 0.004447, 0.047784, -0.014133, -0.010186, -0.031019, -0.037784, 0.034803, -0.004528, 0.016277, 0.01417, 0.009715, -0.047864, 0.028679, -0.025643, -0.037408, 0.006458, -0.043139, 0.026516, -0.029284, -0.028405, 0.03697, -0.017144],
        "top_k": 3,
        "rag_table": "tracopp.rag_document_chunks",
        "document_filter": "Sales_Cancellation_KnowledgeBase.pdf"
      },
      {
        "embedding_id": "EMB_002",
        "label": "Shipment Policy",
        "content": "What happens after failed delivery attempts, what is the Return to Origin (RTO) process, and how long does the customer wait for a refund after RTO?",
        "embedding": [-0.009602, -0.029992, -0.03212, -0.025157, 0.025988, -0.024885, -0.011693, 0.018431, 0.003863, 0.043838, -0.001073, -0.007836, 0.011322, -0.028331, 0.0402, -0.012602, -0.011189, 0.018237, -0.034772, 0.016057, 0.034997, -0.016119, 0.044686, 0.002872, 0.027447, -0.003096, -0.009738, -0.02306, -0.049238, -0.029624, 0.048957, 0.003431, -0.003791, 0.040024, 0.010551, 0.047671, -0.014248, -0.028418, 0.042076, -0.033919, 0.029184, 0.009542, 0.048289, 0.044391, 0.01603, -0.046294, -0.04767, -0.002627, 0.031967, -0.041884, -0.007458, -0.041398, -0.019019, -0.049433, -0.01703, 0.00234, -0.029921, 0.028722, -0.04446, -0.028856, -0.024242, -0.009593, 0.026379, -0.014619, 0.0195, 0.04222, -0.036907, 0.036393, 0.009967, 0.024722, 0.010803, -0.00917, -0.040352, -0.035634, -0.032586, -0.032235, -0.035449, -0.029242, 0.006097, 0.027057, 0.029797, 0.034613, -0.038279, 0.032235, -0.031405, -0.042761, -0.021229, 0.008569, -0.045232, -0.028368, -0.01009, 0.032237, -0.010059, -0.008593, -0.012902, -0.040734, 0.037957, 0.042304, 0.022166, -0.010142, -0.005603, -0.018858, 0.015433, 0.015336, -0.018934, 0.037423, 0.022073, -0.02814, 0.030927, 0.01743, -0.025028, -0.020362, 0.025151, -0.041987, -0.006218, 0.046381, -0.024379, 0.000315, 0.040721, 0.037459, 0.02882, 0.003324, 0.042983, -0.024316, 0.038158, -0.009067, 0.015822, 0.0111, -0.021771, 0.017824, 0.010428, 0.048729, 0.016678, -0.005995, -0.012018, 0.038748, -0.015462, 0.016706, 0.019434, 0.046465, -0.030672, 0.016501, -0.032834, 0.014006, 0.015717, 0.024302, 0.036628, -0.026876, 0.036051, -0.015446, -0.01001, -0.038767, 0.003175, -0.049871, -0.018947, 0.01723, 0.024754, -0.033264, 0.028487, -0.005588, -0.02947, 0.024858, 0.023893, -0.003198, 0.003103, 0.01198, 0.01317, 0.026504, 0.026894, -0.029972, -0.047938, -0.039485, -0.01925, 0.008051, 0.046114, -0.008323, -0.013077, 0.005723, 0.044831, 0.008801, -0.020483, 0.025666, 0.049182, 0.029362, -0.010155, -0.032775, -0.003918, -0.037153, -0.036934, -0.005345, 0.035022, 0.020184, -0.008184, 0.045433, -0.032117, -0.024983, -0.022642, 0.007266, 0.038976, -0.011735, 0.032667, 0.043695, -0.002083, 0.039293, 0.038927, -0.002365, -0.033052, -0.042525, -0.026043, -0.004013, -0.048459, -0.017025, -0.000588, -0.016425, 0.023373, 0.006962, 0.003301, 0.013351, 0.008294, -0.008606, -0.033402, 0.008814, -0.045251, -0.046386, -0.015761, -0.027004, 0.025552, -0.034148, -0.006092, 0.019554, -0.008228, 0.030535, -0.038283, -0.032816, -0.022451, -0.013483, 0.00597, -0.030176, 0.0059, 0.020182, 0.01526, 0.03152, -0.041854, 0.017787, 0.022475, 0.032507, -0.03498, -0.041349, 0.025918, 0.014661, -0.033344, 0.037087, 0.021694, 0.011498, 0.026055, 0.011109, -0.015991, -0.044719, -0.01576, 0.012506, -0.031201, -0.032042, -0.038886, -0.000344, 0.046664, 0.023069, -0.048746, -0.012316, 0.018212, -0.040303, 0.029486, -0.026465, -0.005615, 0.029294, 0.03742, -0.041982, 0.031727, 0.037543, 0.033858, 0.027405, -0.012688, -0.01866, -0.04544, -0.010347, -0.019936, -0.034117, 0.044364, 0.038096, 0.030968, -0.020427, -0.03764, -0.00725, -0.04277, -0.014626, 0.010648, -0.018267, -0.016547, -0.017305, 0.032905, -0.046543, 0.031389, 0.011027, 0.004798, 0.019363, -0.048146, 0.03631, -0.021123, -0.010046, 0.001227, 0.040124, -0.027217, 0.002412, 0.049164, -0.028784, 0.014781, -0.033616, 0.006718, -0.006529, 0.006556, -0.047129, -0.029796, 0.040057, -0.032025, -0.019953, 0.04892, -0.02454, 0.007975, -0.006937, -0.049678, 0.014357, 0.000298, 0.043694, 0.047666, -0.042598, 0.008823, -0.015868, -0.036791, 0.041693, -0.040901, 0.000196, -0.026738, 0.007288, -0.02916, 0.035474, -0.006366, -0.029832, 0.030065, -0.036539, 0.023815, -0.025158, 0.03409, -0.024347, 0.015147, 0.017225, 0.00045, 0.037067, 0.004322, -0.026526, 0.002449, 0.01871, -0.0079, 0.002437, -0.042752, -0.02495, 0.026712, -0.016581, -0.031091, 0.029346, -0.04704, -0.046176, -0.043785, -0.031038, -0.045003, -0.020715, -0.023177, 0.042313, -0.024508, 0.007725, -0.020467, 0.022569, -0.038592, -0.015543, -0.035771, -0.019494, -0.023962, -0.004761, 0.044355, -0.047278, -0.02684, 0.010827, 0.033482, -0.012041, -0.014116, -0.018202, -0.012473, 0.003831, 0.02798, -0.047846, -0.032406, -0.027788, 0.012073, 0.026054, -0.042954, -0.049926, -0.038604, -0.006415, 0.019188, 0.047266, -0.013023, -0.007625, 0.037608, 0.026767, 0.040431, -0.023718, 0.021208, 0.03084, -0.022673, -0.025653, 0.043032, -0.028029, -0.017394, -0.039753, 0.03763, 0.012135, -0.02569, -0.005774, -0.00553, -0.048314, 0.02437, -0.042236, -0.011658, 0.023771, -0.02177, 0.026457, 0.04021, 0.020395, -0.007418, 0.042948, -0.01791, 0.049637, 0.010497, 0.003459, 0.037153, -0.039416, -0.021346, 0.027514, -0.043188, 0.042528, -0.004623, -0.000992, 0.049612, -0.041488, -0.048016, 0.00631, 0.013424, 0.036245, -0.030763, 0.038319, 0.015768, 0.007873, -0.048041, 0.029934, -0.028193, 0.016777, 0.049331, -0.048728, -0.007028, 0.043857, -0.021312, 0.033791, 0.031895, 0.019072, 0.049832, 0.020566, -0.039532, 0.03419, 0.025176, -0.011385, -0.040371, -0.023102, 0.002639, -0.024981, 0.048669, -0.034169, -0.022587, -0.037636, 0.024856, 0.03284, -0.024919, -0.010884, 0.038842, 0.009773, -0.028249, 0.049681, 0.026962, -0.019337, -0.005212, 1e-05, 0.013452, -0.004055, -0.035098, -0.017088, -0.037125, 0.000249, 0.011365, 0.010187, -0.042943, 0.005579, 0.028136, 0.007291, -0.016224, 0.028541, -0.010045, 0.029343, -0.048946, -0.041158, -0.00421, -0.041634, -0.03049, 0.043322, 0.027668, -0.020128, -0.038547, 0.02314, 0.020807, -0.032677, 0.005497, 0.014115, -0.0411, -0.038844, -0.047486, 0.033752, -0.020223, -0.016522, -0.045718, 0.014872, -0.024989, 0.004226, -0.015056, -0.015189, -0.045698, -0.017491, 0.041267, 0.044322, 0.041393, 0.035082, 0.031097, 0.012806, 0.010486, 0.021836, 0.046053, 0.010374, 0.005738, 0.022849, 0.034495, 0.00339, -0.047946, 0.010589, -0.015596, -0.037169, -0.045421, 0.003393, 0.045504, 0.005807, 0.033401, -0.032701, -0.01711, 0.045525, 0.018874, 0.02267, -0.020442, 0.016796, -0.015684, -0.030134, -0.034243, -0.032446, -0.040753, -0.010899, 0.036752, 0.00448, -0.012737, 0.014153, 0.042222, -0.024104, 0.041849, 0.048178, -0.014826, -0.043689, 0.018103, 0.041906, -0.013227, -0.018659, -0.026311, -0.037578, 0.016412, -0.021069, 0.043324, -0.009217, -0.037107, 0.016699, 0.048159, -0.037035, 0.047007, 0.016149, 0.026773, 0.044547, 0.004811, 0.003504, -0.035758, -0.00887, 0.005241, -0.023488, -0.006579, -0.01161, 0.033763, -0.015438, 0.039625, -0.027153, 0.015123, -2.1e-05, -0.019848, 0.027949, 0.048883, -0.037313, 0.031122, -0.043011, -0.014495, 0.045695, 0.046513, 0.042699, -0.014472, 0.024034, 0.047716, -0.043537, 0.032821, 0.022431, 0.043216, -0.004896, 0.014323, 0.026201, -0.000338, 0.021823, -0.028337, -0.045533, -0.027983, 0.048528, -0.006858, 0.038815, 0.047031, 0.041676, 0.004931, -0.021149, 0.01088, 0.027019, 0.022232, -0.046738, -0.044346, -0.046742, -0.025083, -0.010655, -0.012859, 0.025973, 0.026428, -0.021577, -0.015138, 0.03909, 0.019138, -0.046809, -0.017033, 0.032345, 0.003627, -0.029911, -0.00851, 0.017665, -0.032245, -0.024594, 0.034083, -0.011084, -0.008754, 0.048962, 0.045803, -0.019668, -0.049989, -0.032809, 0.04755, 0.020236, -0.026821, 0.040427, 0.037707, 0.021215, -0.048221, 0.002857, -0.027761, -0.024419, -0.010658, -0.00989, 0.038422, -0.012546, -0.033408, -0.034424, -0.003634, -0.022237, 0.033936, 0.012984, 0.023152, -0.032266, 0.006679, 0.019074, -0.045175, -0.010106, 0.01681, -0.034665, 0.045709, -0.0288, -0.038228, 0.018765, 0.048538, 0.027315, 0.003197, -0.01715, -0.028447, -0.043562, -0.027616, 0.012869, -0.025263, 0.048848, -0.03433, -0.025552, -0.009243, 0.045386, -0.015887, -0.031545, 0.022476, -0.041384, -0.002928, -0.028473, 0.047592, -0.006229, 0.000565, 0.045609, 0.015241, 0.049249, -0.007134, 0.037221, -0.006544, -0.022299, 0.046081, 0.012298, -0.035662, 0.006871, 0.01911, -0.036419, -0.001652, -0.005601, -0.031671, 0.018663, -0.001281, 0.009579, 0.003575, 0.011465, 0.0279, -0.001611, 0.046497, 0.040232, -0.004548, -0.03787, -0.001017, -0.0119, 0.03887, -0.018563, -0.044017, -0.030467, 0.037785, -0.037827, 0.040965, -0.007035, 0.0041, 0.025462, 0.03675, -0.038702, 0.008874, -0.031119, 0.045467, 0.02714, -0.024615, -0.015408, 0.047585, 0.045818, 0.0267, -0.046102, -0.028028, 0.010334, -0.029335, 0.001707, -0.049355, -0.003872, -0.002373, 0.032867, -0.015323, 0.040015, -0.025611, -0.048261, -0.004814, -0.033258, 0.045506, 0.032202, 0.043599, -0.02865, 0.037484, 0.041412, -0.021764, 0.031495, -0.013121, -0.031381, 0.017649, -0.016572, -0.01984, 0.014458, 0.014833, -0.048543, -0.047132, 0.003594, -0.040982, -0.039191, 0.043451, 0.045202, 0.021173, 0.042366, 0.019, 0.042633, -0.049647, -0.012733, -0.013462, -0.016091, -0.023042, -0.018009, 0.024371, 0.044936, 0.042207, -0.010989, 0.010305, -0.026922, -0.019128, 0.041151, 0.003852, -0.04122, -0.00182, 0.028901, 0.018085, -0.038855, -0.011124, -0.017914, -0.027913, -0.02544, 0.033775, 0.005331, 0.0303, -0.01034, 0.034205, -0.049276, -0.015884, -0.030933, -0.023143, 0.023517, -0.032121, 0.037794, 0.007924, 0.037567, -0.04771, -0.04382, -0.046706, 0.048706, -0.003069, -0.044027, -0.021239, -0.014606, -0.024112, -0.018498, -0.026087, -0.025162, -0.00684, -0.0387, 0.009825, 0.030722, -0.032403, 0.013709, 0.018583, -0.018328, -0.011553, -0.036027, 0.011604, 0.047823, 0.027664, -0.028533, -0.007189, 0.000959, -0.021921, 0.046325, 0.037815, -0.005368, -0.027328, 0.025267, 0.001858, 0.021488, 0.037461, 0.047158, 0.02849, -0.029477, 0.005371, 0.021772, -0.032526, 0.048918, -0.022795, 0.03484, -0.048523, -0.041292, -0.048429, -0.041239, -0.042548, -0.042103, 0.022326, 0.042053, 0.029719, 0.031829, 0.027924, -0.032588, -0.011459, -0.045309, -0.03203, -0.030406, -0.003688, 0.042335, -0.014553, 0.018899, 0.015937, -0.019274, -0.045729, -0.028358, -0.029948, 0.001523, -0.018381, 0.015184, 0.011223, -0.038928, 0.035997, -0.008368, -0.028863, -0.04663, -0.001952, -0.038082, 0.0253, -0.029825, -0.032875, -0.007387, -0.042258, 0.04098, 0.035577, -0.041966, -0.025787, 0.033314, 0.026788, 0.003573, 0.017696, -0.005932, 0.010826, 0.011943, 0.024408, 0.047183, 0.001902, -0.037009, 0.027052, 0.047413, 0.003727, 0.043383, 0.025198, 0.02507, 0.029291, 0.010789, -0.039129, -0.036485, 0.036833, 0.014241, -0.032862, -0.02645, 0.037467, -0.037464, 0.008557, 0.026046, -0.020891, -0.04836, -0.011484, 0.017108, 0.037823, 0.009838, -0.042786, -0.030222, 0.000912, -0.024794, -0.036731, -0.034545, 0.028061, -0.0151, 0.035169, 0.045669, -0.015663, 0.017341, -0.029026, -0.02218, -0.027798, 0.000714, -0.039838, 0.030646, 0.019823, -0.037484, -0.022178, -0.024287, 0.044406, 0.039979, -0.028495, 0.012244, 0.025146, 0.002177, -0.021959, 0.035016],
        "top_k": 3,
        "rag_table": "tracopp.rag_document_chunks",
        "document_filter": "Sales_Shipment_KnowledgeBase.pdf"
      }
    ]
  },
  "execution_flow": {
    "steps": ["validate_json", "execute_sql", "retrieve_rag", "synthesize", "render_output"],
    "parallel_sql_execution": true,
    "parallel_rag_execution": true,
    "stop_on_critical_error": false,
    "timeout_seconds": 120
  },
  "synthesis_instruction": {
    "treat_structured_as": "source_of_truth",
    "treat_unstructured_as": "policy_and_guidance",
    "conflict_resolution": "structured_data_wins",
    "response_language": "English",
    "response_tone": "professional",
    "include_recommendations": true,
    "include_confidence_score": false,
    "max_response_length": "detailed",
    "focus_areas": ["cancellation_patterns", "carrier_performance", "policy_compliance", "operational_recommendations"]
  },
  "expected_output_schema": {
    "sections": [
      {
        "section_id": "structured_summary",
        "title": "Structured Data Summary",
        "display_type": "table_and_chart",
        "chart_type": "bar",
        "source": "sql"
      },
      {
        "section_id": "policy_guidance",
        "title": "Policy & Guidance",
        "display_type": "text",
        "source": "llm"
      },
      {
        "section_id": "synthesized_answer",
        "title": "Synthesized Answer",
        "display_type": "text",
        "source": "llm"
      },
      {
        "section_id": "recommendations",
        "title": "Recommendations",
        "display_type": "list",
        "source": "llm"
      }
    ]
  },
  "error_handling": {
    "on_sql_error": "continue_with_warning",
    "on_rag_error": "continue_with_warning",
    "on_llm_error": "return_partial_results",
    "max_retries": 2,
    "fallback_message": "Unable to synthesize a complete response. Partial results are shown below."
  }
};

// ─── Domain colour map ─────────────────────────────────────────────────────────
const DOMAIN_COLORS = {
  Sales:          { bg: 'bg-blue-100',    text: 'text-blue-800',    icon: '💼', hex: '#3b82f6' },
  Finance:        { bg: 'bg-emerald-100', text: 'text-emerald-800', icon: '💰', hex: '#10b981' },
  HR:             { bg: 'bg-purple-100',  text: 'text-purple-800',  icon: '👥', hex: '#8b5cf6' },
  Marketing:      { bg: 'bg-orange-100',  text: 'text-orange-800',  icon: '📣', hex: '#f97316' },
  Operations:     { bg: 'bg-cyan-100',    text: 'text-cyan-800',    icon: '⚙️', hex: '#06b6d4' },
  Procurement:    { bg: 'bg-amber-100',   text: 'text-amber-800',   icon: '🛒', hex: '#f59e0b' },
  Legal:          { bg: 'bg-red-100',     text: 'text-red-800',     icon: '⚖️', hex: '#ef4444' },
  Support:        { bg: 'bg-teal-100',    text: 'text-teal-800',    icon: '🎧', hex: '#14b8a6' },
  Inventory:      { bg: 'bg-lime-100',    text: 'text-lime-800',    icon: '📦', hex: '#84cc16' },
  'Supply Chain': { bg: 'bg-sky-100',     text: 'text-sky-800',     icon: '🔗', hex: '#0ea5e9' },
};
const DEFAULT_DOMAIN = { bg: 'bg-slate-100', text: 'text-slate-800', icon: '🔮', hex: '#6366f1' };

// ─── Progress step definitions ─────────────────────────────────────────────────
const STEPS = [
  { id: 'validate_json', label: 'Validate JSON' },
  { id: 'execute_sql',   label: 'Execute SQL'   },
  { id: 'retrieve_rag',  label: 'Retrieve RAG'  },
  { id: 'synthesize',    label: 'Synthesize'    },
  { id: 'render_output', label: 'Render Output' },
];

// ─── App state ─────────────────────────────────────────────────────────────────
const state = {
  editor: null,
  isRunning: false,
  lastResults: null,
  logs: [],
  activeTab: 'dashboard',
  stepStatus: Object.fromEntries(STEPS.map(s => [s.id, 'pending'])),
  chartInstances: {},
};

// ─── Boot ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  initEditor();
  buildProgressTracker();
  checkHealth();
  setInterval(checkHealth, 30_000);
  setInterval(pollForAgentSubmission, 5_000);
  setupTabListeners();
  showEmptyDashboard();
});

// ─── Editor ────────────────────────────────────────────────────────────────────
function initEditor() {
  const ta = document.getElementById('json-textarea');
  state.editor = CodeMirror.fromTextArea(ta, {
    mode: { name: 'javascript', json: true },
    theme: 'dracula',
    lineNumbers: true,
    autoCloseBrackets: true,
    matchBrackets: true,
    indentUnit: 2,
    tabSize: 2,
    lineWrapping: false,
    extraKeys: { 'Ctrl-Space': 'autocomplete' },
  });
  state.editor.setValue(JSON.stringify(SAMPLE_JSON, null, 2));
  state.editor.on('change', onEditorChange);
  onEditorChange();
}

function onEditorChange() {
  const raw = state.editor.getValue().trim();
  try {
    const parsed = JSON.parse(raw);
    updateDomainBadge(parsed?.app_context?.domain);
    document.getElementById('editor-status').textContent = '✓ Valid JSON';
    document.getElementById('editor-status').className = 'text-xs text-green-600 font-medium';
  } catch {
    document.getElementById('editor-status').textContent = '✗ Invalid JSON';
    document.getElementById('editor-status').className = 'text-xs text-red-500 font-medium';
  }
}

function formatJSON() {
  try {
    const parsed = JSON.parse(state.editor.getValue());
    state.editor.setValue(JSON.stringify(parsed, null, 2));
    showToast('JSON formatted', 'success');
  } catch { showToast('Cannot format — invalid JSON', 'error'); }
}

function clearEditor() {
  if (!confirm('Clear the editor? This cannot be undone.')) return;
  state.editor.setValue('{}');
}

function loadSampleJSON() {
  state.editor.setValue(JSON.stringify(SAMPLE_JSON, null, 2));
  showToast('Sample JSON loaded', 'info');
}

async function generateSampleJSON() {
  const btn = document.getElementById('btn-generate');
  if (!btn || btn.disabled) return;

  btn.disabled = true;
  btn.innerHTML = `<svg class="spin inline-block" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg> Generating…`;
  showToast('Generating new JSON — this may take 15–30 seconds…', 'info');

  try {
    const res = await fetch('/api/generate-sample-json', { method: 'POST' });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(`Generation failed: ${data.error || res.statusText}`, 'error');
      return;
    }

    state.editor.setValue(JSON.stringify(data, null, 2));
    showToast('New scenario generated and loaded ✓', 'success');
  } catch (e) {
    showToast(`Network error: ${e.message}`, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="inline flex-shrink-0"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg> Generate`;
  }
}

// ─── Domain badge ──────────────────────────────────────────────────────────────
function updateDomainBadge(domain) {
  const c = DOMAIN_COLORS[domain] || DEFAULT_DOMAIN;
  const badge = document.getElementById('domain-badge');
  if (!badge) return;
  badge.textContent = `${c.icon}  ${domain || 'Unknown'}`;
  badge.className = `px-3 py-1 rounded-full text-sm font-semibold ${c.bg} ${c.text}`;
}

// ─── Progress tracker ──────────────────────────────────────────────────────────
function buildProgressTracker() {
  const container = document.getElementById('progress-tracker');
  container.innerHTML = '';
  STEPS.forEach((step, i) => {
    // Step circle + label
    const wrapper = document.createElement('div');
    wrapper.className = 'flex flex-col items-center gap-1 flex-shrink-0';
    wrapper.innerHTML = `
      <div id="step-${step.id}" class="step-circle pending">
        <span id="step-icon-${step.id}">${i + 1}</span>
      </div>
      <span id="step-label-${step.id}" class="text-xs text-slate-500 font-medium text-center leading-tight" style="max-width:72px">${step.label}</span>
    `;
    container.appendChild(wrapper);

    // Connector (not after last)
    if (i < STEPS.length - 1) {
      const conn = document.createElement('div');
      conn.id = `connector-${step.id}`;
      conn.className = 'step-connector self-center';
      container.appendChild(conn);
    }
  });
}

function resetProgress() {
  STEPS.forEach(s => {
    state.stepStatus[s.id] = 'pending';
    const circle = document.getElementById(`step-${s.id}`);
    const icon   = document.getElementById(`step-icon-${s.id}`);
    const label  = document.getElementById(`step-label-${s.id}`);
    const conn   = document.getElementById(`connector-${s.id}`);
    if (circle) { circle.className = 'step-circle pending'; }
    if (icon)   { icon.innerHTML = STEPS.findIndex(x => x.id === s.id) + 1; }
    if (label)  { label.className = 'text-xs text-slate-500 font-medium text-center leading-tight'; }
    if (conn)   { conn.classList.remove('done'); }
  });
}

function updateStep(stepId, status, message) {
  state.stepStatus[stepId] = status;
  const circle = document.getElementById(`step-${stepId}`);
  const icon   = document.getElementById(`step-icon-${stepId}`);
  const label  = document.getElementById(`step-label-${stepId}`);

  if (!circle) return;

  if (status === 'in_progress') {
    circle.className = 'step-circle active';
    icon.innerHTML = `<svg class="spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>`;
    if (label) { label.className = 'text-xs text-indigo-600 font-semibold text-center leading-tight'; }
  } else if (status === 'completed') {
    circle.className = 'step-circle done';
    icon.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>`;
    if (label) { label.className = 'text-xs text-green-600 font-semibold text-center leading-tight'; }
    // Mark connector as done
    const conn = document.getElementById(`connector-${stepId}`);
    if (conn) conn.classList.add('done');
  } else if (status === 'error') {
    circle.className = 'step-circle error';
    icon.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;
    if (label) { label.className = 'text-xs text-red-500 font-semibold text-center leading-tight'; }
  }

  // Update live message
  const msgEl = document.getElementById('progress-message');
  if (msgEl && message) msgEl.textContent = message;
}

// ─── Health check ──────────────────────────────────────────────────────────────
async function checkHealth() {
  const dot  = document.getElementById('health-dot');
  const text = document.getElementById('health-text');
  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    const ok = d.status === 'healthy';
    if (dot)  { dot.className  = `w-2 h-2 rounded-full ${ok ? 'bg-green-500' : 'bg-amber-400'}`; }
    if (text) { text.textContent = ok ? 'All systems OK' : 'Degraded'; }
  } catch {
    if (dot)  { dot.className  = 'w-2 h-2 rounded-full bg-red-500'; }
    if (text) { text.textContent = 'Offline'; }
  }
}

// ─── Poll for upstream agent submissions ───────────────────────────────────────
async function pollForAgentSubmission() {
  if (state.isRunning) return;
  try {
    const r = await fetch('/api/latest-submission');
    const d = await r.json();
    if (d.new_submission && d.payload) {
      state.editor.setValue(JSON.stringify(d.payload, null, 2));
      showToast('📥 New JSON received from upstream agent!', 'info');
    }
  } catch { /* silently ignore */ }
}

// ─── Validate ──────────────────────────────────────────────────────────────────
async function validateJSON() {
  let payload;
  try { payload = JSON.parse(state.editor.getValue()); }
  catch (e) { showValidationPanel({ valid: false, errors: [`Parse error: ${e.message}`], warnings: [] }); return; }

  const btn = document.getElementById('btn-validate');
  btn.disabled = true; btn.textContent = 'Validating…';

  try {
    const r = await fetch('/api/validate-json', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const d = await r.json();
    showValidationPanel(d);
  } catch (e) {
    showValidationPanel({ valid: false, errors: [`Request failed: ${e.message}`], warnings: [] });
  } finally {
    btn.disabled = false; btn.textContent = 'Validate JSON';
  }
}

function showValidationPanel(result) {
  const panel = document.getElementById('validation-panel');
  if (!panel) return;
  panel.classList.remove('hidden');

  if (result.valid) {
    const warnCount = result.warnings?.length || 0;
    panel.innerHTML = `<div class="validation-ok">
      <p class="text-sm font-semibold text-green-700">✓ JSON is valid${warnCount ? ` (${warnCount} warning${warnCount > 1 ? 's' : ''})` : ''}</p>
      ${(result.warnings || []).map(w => `<p class="text-xs text-amber-600 mt-1">⚠ ${w}</p>`).join('')}
    </div>`;
  } else {
    panel.innerHTML = `<div class="validation-error">
      <p class="text-sm font-semibold text-red-700">✗ Validation failed (${result.errors.length} error${result.errors.length > 1 ? 's' : ''})</p>
      ${result.errors.map(e => `<p class="text-xs text-red-600 mt-1">• ${e}</p>`).join('')}
      ${(result.warnings || []).map(w => `<p class="text-xs text-amber-600 mt-1">⚠ ${w}</p>`).join('')}
    </div>`;
  }
}

// ─── Synthesize (SSE) ──────────────────────────────────────────────────────────
async function runSynthesis() {
  if (state.isRunning) return;

  let payload;
  try { payload = JSON.parse(state.editor.getValue()); }
  catch (e) { showToast(`Invalid JSON: ${e.message}`, 'error'); return; }

  state.isRunning = true;
  state.logs = [];
  state.lastResults = null;
  resetProgress();
  clearDashboard();
  switchTab('dashboard');

  const btnRun = document.getElementById('btn-run');
  btnRun.disabled = true;
  btnRun.innerHTML = `<svg class="spin inline-block mr-2" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/></svg>Running…`;

  try {
    const response = await fetch('/api/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const err = await response.text();
      showToast(`Server error: ${err}`, 'error');
      return;
    }

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try { handleSSEEvent(JSON.parse(line.slice(6))); }
          catch (e) { console.warn('SSE parse error', e); }
        }
      }
    }
  } catch (e) {
    showToast(`Connection error: ${e.message}`, 'error');
  } finally {
    state.isRunning = false;
    btnRun.disabled = false;
    btnRun.innerHTML = `<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" class="inline-block mr-1"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Synthesis`;
  }
}

function handleSSEEvent(data) {
  if (data.event === 'progress') {
    updateStep(data.step, data.status, data.message || '');

    // Store intermediate data
    if (data.data) {
      if (data.step === 'execute_sql')  state._sqlResults  = data.data;
      if (data.step === 'retrieve_rag') state._ragResults  = data.data;
    }

    // Append warnings to logs
    if (data.data?.warnings?.length) {
      data.data.warnings.forEach(w => addLog('warn', w));
    }

  } else if (data.event === 'error') {
    updateStep(data.step, 'error');
    const errors = data.errors || [data.message];
    const errDiv = document.getElementById('error-panel');
    if (errDiv) {
      errDiv.classList.remove('hidden');
      errDiv.innerHTML = `<div class="validation-error">
        <p class="text-sm font-semibold text-red-700">✗ Error at step: ${data.step}</p>
        ${errors.map(e => `<p class="text-xs text-red-600 mt-1">• ${e}</p>`).join('')}
      </div>`;
    }

  } else if (data.event === 'complete') {
    state.lastResults = data.data;
    renderResults(data.data);
    showToast('Synthesis complete!', 'success');

  } else if (data.event === 'logs') {
    if (Array.isArray(data.data)) {
      state.logs = data.data;
      renderLogsTab(data.data);
    }
  }
}

// ─── Results rendering ─────────────────────────────────────────────────────────
function clearDashboard() {
  const d = document.getElementById('dashboard-content');
  const r = document.getElementById('raw-content');
  const l = document.getElementById('logs-content');
  if (d) d.innerHTML = '';
  if (r) r.innerHTML = '';
  if (l) l.innerHTML = '';
  const ep = document.getElementById('error-panel');
  if (ep) ep.classList.add('hidden');

  // Destroy old chart instances
  Object.values(state.chartInstances).forEach(c => { try { c.destroy(); } catch {} });
  state.chartInstances = {};
}

function showEmptyDashboard() {
  const d = document.getElementById('dashboard-content');
  if (!d) return;
  d.innerHTML = `<div class="empty-state">
    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <p class="text-base font-semibold mt-2">No results yet</p>
    <p class="text-sm mt-1">Paste or edit your JSON on the left, then click <strong>Run Synthesis</strong></p>
  </div>`;
}

function renderResults(results) {
  const { sql_results, rag_results, llm_response, expected_output_schema, execution_meta } = results;
  const sections = expected_output_schema?.sections || [];
  const d = document.getElementById('dashboard-content');
  d.innerHTML = '';

  // Meta banner
  if (execution_meta) {
    const meta = document.createElement('div');
    meta.className = 'flex flex-wrap gap-3 mb-4 fade-in';
    meta.innerHTML = [
      ['⏱ Duration',   `${execution_meta.total_duration_s}s`],
      ['🔢 SQL Queries', execution_meta.sql_queries],
      ['📚 RAG Searches', execution_meta.rag_searches],
      ['❌ SQL Errors',  execution_meta.sql_errors],
    ].map(([k, v]) => `
      <div class="bg-white border border-slate-200 rounded-lg px-3 py-2 text-center">
        <p class="text-xs text-slate-500">${k}</p>
        <p class="text-sm font-bold text-slate-800">${v}</p>
      </div>`).join('');
    d.appendChild(meta);
  }

  // Render each expected section in order
  for (const section of sections) {
    const src = section.source;

    if (src === 'sql' && sql_results?.length) {
      d.appendChild(renderSQLSection(sql_results, section));
    } else if (src === 'rag' && rag_results?.length) {
      d.appendChild(renderRAGSection(rag_results, section));
    } else if (src === 'llm' && llm_response) {
      d.appendChild(renderLLMSection(section, llm_response[section.section_id]));
    }
  }

  // If no schema sections, fall back to rendering everything
  if (!sections.length) {
    if (sql_results?.length)  d.appendChild(renderSQLSection(sql_results, {}));
    if (rag_results?.length)  d.appendChild(renderRAGSection(rag_results, {}));
    if (llm_response)         d.appendChild(renderLLMSection({ section_id: 'synthesized_answer', title: 'Synthesized Answer', display_type: 'text' }, llm_response.synthesized_answer));
  }

  renderRawDataTab(results);
}

// ── SQL section ────────────────────────────────────────────────────────────────
function renderSQLSection(sqlResults, section) {
  const wrapper = document.createElement('div');
  wrapper.className = 'fade-in';

  sqlResults.forEach((result, idx) => {
    const card = document.createElement('div');
    card.className = 'result-card mb-4';

    const statusBadge = result.status === 'success'
      ? `<span class="ml-auto text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700">✓ ${result.row_count} row${result.row_count !== 1 ? 's' : ''}</span>`
      : `<span class="ml-auto text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-600">✗ Error</span>`;

    card.innerHTML = `
      <div class="result-card-header bg-blue-50">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
        <span class="text-blue-800">${result.label || result.query_id}</span>
        <span class="text-xs text-slate-400 font-normal">${result.source_table}</span>
        ${statusBadge}
      </div>
      <div class="result-card-body p-0" id="sql-body-${idx}"></div>
    `;

    const body = card.querySelector(`#sql-body-${idx}`);

    if (result.status === 'error') {
      body.innerHTML = `<div class="p-4 text-sm text-red-600">${result.error}</div>`;
    } else if (!result.rows?.length) {
      body.innerHTML = `<div class="p-4 text-sm text-slate-400 italic">No rows returned.</div>`;
    } else {
      // Tab bar: Table | Chart (if numeric cols exist)
      const numCols = getNumericColumns(result.rows);
      const hasChart = numCols.length > 0 && result.rows.length > 0;

      body.innerHTML = `
        <div class="flex border-b border-slate-100 px-2 pt-1">
          <button class="tab-btn active" data-tab="table-${idx}" onclick="switchSqlTab(this,'table-${idx}','chart-${idx}')">Table</button>
          ${hasChart ? `<button class="tab-btn" data-tab="chart-${idx}" onclick="switchSqlTab(this,'chart-${idx}','table-${idx}')">Chart</button>` : ''}
        </div>
        <div id="table-${idx}" class="overflow-auto" style="max-height:260px">
          ${buildTableHTML(result.rows, result.columns)}
        </div>
        ${hasChart ? `<div id="chart-${idx}" class="hidden p-4">
          <div class="chart-container"><canvas id="canvas-${idx}"></canvas></div>
        </div>` : ''}
      `;

      if (hasChart) {
        // Chart renders when tab clicked for first time
        const chartTab = body.querySelector(`[data-tab="chart-${idx}"]`);
        if (chartTab) {
          chartTab.addEventListener('click', () => buildChart(`canvas-${idx}`, result.rows, result.columns), { once: true });
        }
      }
    }

    wrapper.appendChild(card);
  });

  return wrapper;
}

function switchSqlTab(btn, showId, hideId) {
  const show = document.getElementById(showId);
  const hide = document.getElementById(hideId);
  if (show) show.classList.remove('hidden');
  if (hide) hide.classList.add('hidden');
  // Update tab button active states
  const parent = btn.closest('.result-card-body') || btn.parentElement;
  parent.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
}

// ── RAG section ────────────────────────────────────────────────────────────────
function renderRAGSection(ragResults, section) {
  const wrapper = document.createElement('div');
  wrapper.className = 'fade-in';

  ragResults.forEach(result => {
    const card = document.createElement('div');
    card.className = 'result-card mb-4';

    const statusBadge = result.status === 'success'
      ? `<span class="ml-auto text-xs px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">📄 ${result.chunk_count} chunk${result.chunk_count !== 1 ? 's' : ''}</span>`
      : `<span class="ml-auto text-xs px-2 py-0.5 rounded-full bg-red-100 text-red-600">✗ Error</span>`;

    card.innerHTML = `
      <div class="result-card-header bg-amber-50">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
        <span class="text-amber-800">${result.label || result.embedding_id}</span>
        ${result.document_filter ? `<span class="text-xs text-slate-400 font-normal truncate max-w-[160px]">${result.document_filter}</span>` : ''}
        ${statusBadge}
      </div>
      <div class="result-card-body">
        <p class="text-xs text-slate-500 italic mb-3">"${result.content}"</p>
        ${result.status === 'error'
          ? `<div class="text-sm text-red-600">${result.error}</div>`
          : (result.chunks || []).map((chunk, i) => `
            <div class="chunk-card">
              <div class="flex items-center gap-2 mb-2">
                <span class="text-xs font-semibold text-slate-600">Chunk ${i + 1}</span>
                ${chunk.page_number != null ? `<span class="text-xs text-slate-400">Page ${chunk.page_number}</span>` : ''}
                ${chunk.similarity_score != null ? `<span class="ml-auto text-xs font-mono px-2 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">sim: ${parseFloat(chunk.similarity_score).toFixed(4)}</span>` : ''}
              </div>
              <p class="text-sm text-slate-700 leading-relaxed">${escapeHtml(String(chunk.chunk_text || ''))}</p>
            </div>`).join('')
        }
      </div>
    `;
    wrapper.appendChild(card);
  });

  return wrapper;
}

// ── LLM section ────────────────────────────────────────────────────────────────
function renderLLMSection(section, content) {
  if (!content) return document.createDocumentFragment();

  const card = document.createElement('div');
  card.className = 'result-card mb-4 fade-in';

  const headerColors = {
    synthesized_answer: { bg: 'bg-indigo-50', icon: '🧠', stroke: '#6366f1', text: 'text-indigo-800' },
    recommendations:    { bg: 'bg-teal-50',   icon: '💡', stroke: '#14b8a6', text: 'text-teal-800' },
    policy_guidance:    { bg: 'bg-amber-50',  icon: '📋', stroke: '#f59e0b', text: 'text-amber-800' },
  };
  const hc = headerColors[section.section_id] || { bg: 'bg-purple-50', icon: '✨', stroke: '#8b5cf6', text: 'text-purple-800' };

  let bodyHTML = '';
  if (Array.isArray(content)) {
    bodyHTML = `<ul class="space-y-2">
      ${content.map(item => `<li class="flex gap-2 text-sm text-slate-700"><span class="text-teal-500 mt-0.5 flex-shrink-0">✓</span><span>${escapeHtml(String(item))}</span></li>`).join('')}
    </ul>`;
  } else {
    bodyHTML = `<div class="llm-prose">${formatLLMText(String(content))}</div>`;
  }

  card.innerHTML = `
    <div class="result-card-header ${hc.bg}">
      <span class="text-lg">${hc.icon}</span>
      <span class="${hc.text}">${section.title}</span>
    </div>
    <div class="result-card-body">${bodyHTML}</div>
  `;

  return card;
}

// ─── Raw data tab ──────────────────────────────────────────────────────────────
function renderRawDataTab(results) {
  const container = document.getElementById('raw-content');
  if (!container) return;
  container.innerHTML = '';

  const sections = [
    { title: 'SQL Results',        icon: '🗄️',  data: results.sql_results  },
    { title: 'RAG Chunks',         icon: '📚',  data: results.rag_results  },
    { title: 'LLM Response',       icon: '🤖',  data: results.llm_response },
    { title: 'Execution Metadata', icon: '⏱',  data: results.execution_meta },
  ];

  sections.forEach(({ title, icon, data }) => {
    if (!data) return;
    const details = document.createElement('details');
    details.className = 'border border-slate-200 rounded-lg mb-3';
    details.innerHTML = `
      <summary class="cursor-pointer px-4 py-3 font-semibold text-sm text-slate-700 flex items-center gap-2 hover:bg-slate-50 rounded-lg select-none">
        <span>${icon}</span> ${title}
        <span class="ml-auto text-slate-400">▸</span>
      </summary>
      <div class="px-4 pb-4">
        <pre class="bg-slate-900 text-green-300 rounded-lg p-4 text-xs overflow-auto max-h-96 leading-relaxed">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      </div>
    `;
    container.appendChild(details);
  });
}

// ─── Logs tab ──────────────────────────────────────────────────────────────────
function renderLogsTab(logs) {
  const container = document.getElementById('logs-content');
  if (!container) return;
  container.innerHTML = logs.length
    ? logs.map(l => `<div class="log-entry log-${l.level}">
        <span class="text-slate-400">[${l.time.toFixed(3)}s]</span>
        <span class="font-semibold uppercase">${l.level}</span>
        <span>${escapeHtml(l.message)}</span>
      </div>`).join('')
    : '<p class="text-slate-400 text-sm italic p-4">No logs yet.</p>';
}

function addLog(level, message) {
  const container = document.getElementById('logs-content');
  if (!container) return;
  const entry = document.createElement('div');
  entry.className = `log-entry log-${level}`;
  entry.textContent = `[live] ${level.toUpperCase()} — ${message}`;
  container.appendChild(entry);
}

// ─── Tab management ────────────────────────────────────────────────────────────
function setupTabListeners() {
  document.querySelectorAll('[data-main-tab]').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.mainTab));
  });
}

function switchTab(tab) {
  state.activeTab = tab;
  document.querySelectorAll('[data-main-tab]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mainTab === tab);
  });
  ['dashboard', 'raw', 'logs'].forEach(t => {
    const panel = document.getElementById(`${t}-panel`);
    if (panel) panel.classList.toggle('hidden', t !== tab);
  });
}

// ─── Chart builder ─────────────────────────────────────────────────────────────
function getNumericColumns(rows) {
  if (!rows?.length) return [];
  const first = rows[0];
  return Object.entries(first)
    .filter(([, v]) => typeof v === 'number' || (v !== null && !isNaN(Number(v))))
    .map(([k]) => k);
}

function getLabelColumn(rows) {
  if (!rows?.length) return null;
  const first = rows[0];
  const strCols = Object.entries(first)
    .filter(([, v]) => typeof v === 'string' && v.length < 40)
    .map(([k]) => k);
  return strCols[0] || null;
}

function buildChart(canvasId, rows, columns) {
  const ctx = document.getElementById(canvasId)?.getContext('2d');
  if (!ctx) return;

  const numCols  = getNumericColumns(rows);
  const labelCol = getLabelColumn(rows);
  const labels   = rows.map((r, i) => labelCol ? String(r[labelCol]).substring(0, 20) : `Row ${i + 1}`);
  const COLORS   = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#3b82f6', '#8b5cf6'];

  const datasets = numCols.slice(0, 4).map((col, i) => ({
    label: col,
    data: rows.map(r => Number(r[col]) || 0),
    backgroundColor: COLORS[i % COLORS.length] + '90',
    borderColor: COLORS[i % COLORS.length],
    borderWidth: 1.5,
    borderRadius: 4,
  }));

  if (state.chartInstances[canvasId]) {
    try { state.chartInstances[canvasId].destroy(); } catch {}
  }

  state.chartInstances[canvasId] = new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { labels: { font: { family: 'Inter', size: 11 } } } },
      scales: {
        x: { ticks: { font: { family: 'Inter', size: 11 } } },
        y: { ticks: { font: { family: 'Inter', size: 11 } }, beginAtZero: true },
      },
    },
  });
}

// ─── Table builder ─────────────────────────────────────────────────────────────
function buildTableHTML(rows, columns) {
  if (!rows?.length) return '<p class="text-slate-400 text-sm italic p-4">No rows returned.</p>';
  const cols = columns || Object.keys(rows[0]);
  return `<table class="data-table">
    <thead><tr>${cols.map(c => `<th>${escapeHtml(c)}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(r => `<tr>${cols.map(c => `<td title="${escapeHtml(String(r[c] ?? ''))}">${escapeHtml(String(r[c] ?? ''))}</td>`).join('')}</tr>`).join('')}</tbody>
  </table>`;
}

// ─── Copy / Download ───────────────────────────────────────────────────────────
function copyFinalAnswer() {
  if (!state.lastResults?.llm_response) { showToast('No results to copy yet', 'warning'); return; }
  const text = JSON.stringify(state.lastResults.llm_response, null, 2);
  navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard!', 'success'));
}

function downloadOutput() {
  if (!state.lastResults) { showToast('No results to download yet', 'warning'); return; }
  const blob = new Blob([JSON.stringify(state.lastResults, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `synthesizer-output-${Date.now()}.json`;
  a.click();
  showToast('Downloading JSON output…', 'info');
}

// ─── Toast notification ────────────────────────────────────────────────────────
let _toastTimer;
function showToast(message, type = 'info') {
  const toast = document.getElementById('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.className = `show ${type}`;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { toast.className = toast.className.replace(' show', ''); }, 3000);
}

// ─── Helpers ───────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function formatLLMText(text) {
  const lines = text.split('\n');
  const out   = [];
  let inUL    = false;

  const inlineFormat = str =>
    escapeHtml(str)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>');

  for (const raw of lines) {
    const line = raw.trimEnd();

    if (line.startsWith('## ')) {
      if (inUL) { out.push('</ul>'); inUL = false; }
      out.push(`<h2 class="text-base font-bold text-slate-800 mt-5 mb-2 pb-1 border-b border-slate-200">${inlineFormat(line.slice(3))}</h2>`);
    } else if (line.startsWith('### ')) {
      if (inUL) { out.push('</ul>'); inUL = false; }
      out.push(`<h3 class="text-sm font-semibold text-slate-700 mt-3 mb-1">${inlineFormat(line.slice(4))}</h3>`);
    } else if (/^[-•*] /.test(line)) {
      if (!inUL) { out.push('<ul class="list-disc pl-5 space-y-1 my-2">'); inUL = true; }
      out.push(`<li class="text-sm text-slate-700 leading-relaxed">${inlineFormat(line.replace(/^[-•*] /, ''))}</li>`);
    } else if (/^\d+\. /.test(line)) {
      if (inUL) { out.push('</ul>'); inUL = false; }
      out.push(`<p class="text-sm text-slate-700 leading-relaxed ml-1">${inlineFormat(line)}</p>`);
    } else if (line.trim() === '') {
      if (inUL) { out.push('</ul>'); inUL = false; }
    } else {
      if (inUL) { out.push('</ul>'); inUL = false; }
      out.push(`<p class="text-sm text-slate-700 leading-relaxed mb-1">${inlineFormat(line)}</p>`);
    }
  }
  if (inUL) out.push('</ul>');
  return out.join('\n');
}
