/*
 * Letter content for the Write to the Board page (English and Spanish).
 *
 * Each letter is assembled from random pieces of the chosen issue:
 *   greeting, one opening, the writer's "who" line, two concerns, two facts,
 *   one ask, the shared moratorium paragraph (unless the issue is the closures
 *   issue itself), one closing, sign-off.
 * In openings, {x} is replaced with the issue's topic. In Spanish, {a_x} becomes
 * "al ..." or "a ..." to agree with the topic.
 * In "who" lines, {name} is replaced with the writer's name.
 * Text in [brackets] is a placeholder the writer is asked to replace.
 */
window.LETTER_CONTENT = {
  "board": [
    "pinkardn@district65.net",
    "vannostrandc@district65.net",
    "andersonp2@district65.net",
    "hernandezs2@district65.net",
    "opdyckem@district65.net",
    "wilkinsm@district65.net",
    "wymera@district65.net",
    "schoolboard@district65.net"
  ],
  "en": {
    "ui": {
      "h1a": "Write to the",
      "h1b": "School Board.",
      "lead": "Choose the issue that matters most to you and we’ll draft a letter about it. Add a line of your own and send it from your email. It takes about two minutes.",
      "s0": "What matters most to you?",
      "s0h": "Pick one. Your letter will focus on it.",
      "s1": "Who are you?",
      "name": "Your name",
      "namePh": "First and last name",
      "role": "I am…",
      "roles": [
        "A District 65 parent or caregiver",
        "A District 65 educator or staff member",
        "A community member who cares about District 65"
      ],
      "s2": "Your letter",
      "to": "To",
      "toList": "All 7 D65 board members and schoolboard@district65.net",
      "toNote": "Your email goes out from your own account, so board members can reply to you.",
      "subject": "Subject",
      "body": "Message",
      "shuffle": "↻ Try another version",
      "hint": "Every letter is put together from different pieces about the issue you chose, so no two are alike. Replace the text in [brackets] with a sentence of your own: personal letters carry the most weight.",
      "s3": "Send it",
      "needName": "Please add your name first.",
      "brackets": "Your letter still has text in [brackets]. Replace it with your own words, or tap the button again to send it as is.",
      "opened": "Your email should open in a new tab or app. Review it and press Send. Thank you!",
      "copied": "Copied! Paste it into a new email to the addresses above.",
      "copyFail": "Couldn’t copy automatically. Select the message and copy it by hand.",
      "swapped": "New letter drafted for this issue. Any edits you made to the previous one were replaced.",
      "priv": "Privacy: nothing you type here is saved or sent to us. This page only prepares an email that you send yourself.",
      "copyHead": "To: ",
      "copySubj": "Subject: ",
      "greet": "Dear Board Members,",
      "signoff": "Sincerely,",
      "namePlace": "[Your name]",
      "send": "Send",
      "copy": "Copy",
      "copyS": "For Outlook, Yahoo or any other email",
      "dsub": "Opens a ready-to-send Gmail draft",
      "dnote": "Send opens Gmail in a new tab with the recipients, subject and letter filled in. Just press Send there. Use a different email? Click Copy and paste everything into a new message.",
      "msub": "Opens your email app, ready to send",
      "mnote": "Send opens your phone’s email app with everything filled in. Just press Send there. If the wrong app opens or nothing happens, tap Copy and paste the letter into a new email."
    },
    "openings": [
      "I am writing because {x} must be addressed before this proposal moves forward.",
      "Please reconsider the current proposal and give {x} the careful public review it deserves.",
      "I want a sustainable district, and I am concerned about how this proposal addresses {x}."
    ],
    "who": [
      "My name is {name}. I am a District 65 parent or caregiver who wants students to thrive. [Add a sentence about your child or school.]",
      "My name is {name}. I am an educator or school staff member who cares about students and the people who support them. [Add a sentence about your work.]",
      "My name is {name}. I am a community member who cares about strong public schools and responsible public decisions. [Add a sentence about why this matters to you.]"
    ],
    "common": "Please reject the proposal in its current form and establish a moratorium on school closures until multiple financially credible alternatives, including maintaining the current school footprint, and their student impacts have been independently reviewed, published, and discussed with all affected communities. Please also set a public work plan and review milestones so this pause produces a better, accountable plan.",
    "closings": [
      "Please share what you will do to address these concerns before the next decision. Thank you for your time.",
      "Thank you for considering my concerns and helping create a plan the community can understand and support.",
      "I would appreciate a written response explaining the next steps and how the community can participate."
    ],
    "issues": [
      {
        "title": "School closures and a moratorium",
        "desc": "Pause closures until real alternatives are compared.",
        "topic": "school closures",
        "closures": true,
        "subjects": [
          "Pause closures until alternatives are verified",
          "Our schools deserve a complete plan",
          "Vote no on the current closure proposal",
          "Compare alternatives before closing schools",
          "A moratorium for responsible school planning"
        ],
        "concerns": [
          "Closing schools before a full comparison of alternatives could commit families to avoidable disruption.",
          "Receiving schools deserve a clear assessment of staffing, space, and student support.",
          "Walkable neighborhood schools matter to families across the district.",
          "Retaining a building does not guarantee that it will reopen as a school.",
          "Students should not bear the risks of assumptions that have not been independently tested."
        ],
        "facts": [
          "D65 proposes closing Dewey and Lincolnwood at the end of the 2026–27 school year.",
          "D65 describes November 9 as a plan vote, with closure hearings and later final action still to follow.",
          "The district proposes retaining both school sites and exploring a potential November 2028 bond referendum.",
          "The community demand letter calls for comparison of multiple sustainable options, including maintaining the current school footprint."
        ],
        "asks": [
          "Please establish a moratorium on closures until verified alternatives and student impacts have been publicly reviewed by all affected communities.",
          "Please publish comparable options, including maintaining the current school footprint, with recurring savings, transition costs, and educational effects.",
          "Please require independent financial and student-impact review before any final closure approval, with public review milestones.",
          "Please vote no on the proposal as presented and direct a joint community process to develop a financially credible alternative."
        ]
      },
      {
        "title": "Community participation and shared planning",
        "desc": "Give every community a real voice in the plan.",
        "topic": "community participation",
        "closures": false,
        "subjects": [
          "Give every community a meaningful voice",
          "Build the plan with the community",
          "Community input must be able to change the outcome",
          "A shared vision before permanent changes",
          "Include families before decisions are made"
        ],
        "concerns": [
          "A meeting about how to implement a proposal is different from an opportunity to shape alternatives.",
          "Families at receiving schools need an equal opportunity to understand and influence changes.",
          "Residents without enrolled children also have a stake in the district’s future.",
          "Language, work schedules, and disability access should not determine whose voice is heard.",
          "Public feedback needs a visible connection to board decisions."
        ],
        "facts": [
          "The demand letter requests participation from residents across Evanston and Skokie, including those without enrolled children.",
          "D65’s plan includes closures, boundary changes, and staffing reductions across the district.",
          "The district has published October 13 and October 23 versions of its proposed boundaries.",
          "The demand letter asks for educational and financial consequences of alternatives to be publicly examined."
        ],
        "asks": [
          "Please create a board, district, city, and community working group with families, educators, and independent financial expertise.",
          "Please keep school closures on hold while all affected communities review and discuss credible alternatives.",
          "Please provide accessible, multilingual opportunities to shape options, and publish how feedback changes the recommendation.",
          "Please publish a decision timeline that allows meaningful review of data and alternatives before final votes."
        ]
      },
      {
        "title": "City coordination and neighborhood access",
        "desc": "Plan schools, housing and transportation together.",
        "topic": "city and district coordination",
        "closures": false,
        "subjects": [
          "Plan schools and housing together",
          "Coordinate before boundaries are finalized",
          "Protect access to neighborhood schools",
          "One community needs coordinated planning",
          "Study the citywide effects before proceeding"
        ],
        "concerns": [
          "Housing growth and school access should be evaluated together.",
          "Longer school routes could undermine families’ ability to live with fewer car trips.",
          "District savings should be considered alongside any new costs for city infrastructure.",
          "Families in affordable housing deserve practical access to schools and programs.",
          "Fixing traffic problems after decisions are made may miss better options earlier in the process."
        ],
        "facts": [
          "Evanston adopted its new comprehensive plan on January 26, 2026.",
          "D65’s proposal changes attendance boundaries beyond the two schools proposed for closure.",
          "The October 23 proposal assigns Dewey TWI to Lincoln and Lincolnwood STEP to Orrington.",
          "D65’s FAQ distinguishes overall population projections from school-age enrollment forecasts."
        ],
        "asks": [
          "Please commission a joint city–district assessment of housing growth, school access, transportation, and infrastructure before final closure decisions.",
          "Please overlay proposed boundaries with approved housing projects, affordable housing, and actual walking routes, and publish the findings.",
          "Please reconcile city growth assumptions and district enrollment forecasts, including realistic estimates for family-sized housing.",
          "Please support a closure moratorium until alternatives and citywide student impacts are verified and discussed with affected communities."
        ]
      },
      {
        "title": "School Age Child Care (SACC)",
        "desc": "Keep reliable, affordable care for working families.",
        "topic": "School Age Child Care",
        "closures": false,
        "subjects": [
          "Keep SACC accessible to working families",
          "Protect reliable school-age childcare",
          "Show the childcare plan before ending SACC",
          "Working families need affordable care",
          "Do not leave families without childcare"
        ],
        "concerns": [
          "Families need dependable care to maintain work schedules.",
          "An alternative is only workable if families can afford it and secure a place.",
          "Children with disabilities need care that can meet their needs.",
          "Changing schools and childcare at the same time could compound disruption.",
          "Families should not have to make employment decisions without clear information about future care."
        ],
        "facts": [
          "D65 proposes closing its School Age Child Care program at the end of the 2026–27 school year.",
          "SACC closure is listed separately from the proposed elementary school closures.",
          "The demand letter calls for disclosure of transition costs and credible alternatives.",
          "The demand letter requests meaningful participation from communities across Evanston and Skokie."
        ],
        "asks": [
          "Please reject SACC closure as presented and evaluate options to maintain affordable, accessible care.",
          "Please publish replacement capacity, fees, subsidies, hours, locations, and disability supports before any SACC closure decision.",
          "Please work with families, SACC staff, the city, and potential providers to compare sustainable service options.",
          "Please require a funded continuity plan so every currently served family has a realistic care option before district services end."
        ]
      },
      {
        "title": "TWI and bilingual parent participation",
        "desc": "Give bilingual families a voice before TWI moves.",
        "topic": "TWI and bilingual parent participation",
        "closures": false,
        "subjects": [
          "Resolve BPAC questions before moving TWI",
          "Give bilingual families a voice in program planning",
          "Keep TWI decisions accountable to families",
          "Review the Dewey TWI relocation process",
          "Pause TWI relocation pending meaningful review"
        ],
        "concerns": [
          "Moving a bilingual program can affect access, relationships, staffing, and family participation.",
          "Families should be able to discuss keeping TWI at Dewey as well as other options.",
          "The absence of an active BPAC raises unresolved questions about the program-planning process.",
          "A meeting focused on a possible closure may not provide a full comparison of program alternatives.",
          "Families need to know how their feedback will reach the board before it acts."
        ],
        "facts": [
          "The October 23 proposal would move Dewey’s TWI program to Lincoln.",
          "In an October 29 email, Cecilia Romero stated that D65 does not have an active BPAC.",
          "In her October 30 response, Cecilia Romero said there is no set timeline for BPAC’s formal reestablishment.",
          "Cecilia Romero said ISBE knows about the inactive BPAC; the emails families have seen do not include guidance specifically addressing this relocation."
        ],
        "asks": [
          "Please pause approval of the TWI relocation until parent-participation requirements are clarified and affected families can meaningfully review alternatives.",
          "Please share the ISBE guidance relied on and clarify whether it addresses the specific Dewey TWI relocation.",
          "Please publish a bilingual-program impact assessment covering access, enrollment, staffing, language balance, and continuity.",
          "Please establish an accountable BPAC rebuilding timeline and explain how bilingual families’ recommendations will influence the decision."
        ]
      },
      {
        "title": "Early childhood and Head Start",
        "desc": "Protect continuity for young children and families.",
        "topic": "early childhood services",
        "closures": false,
        "subjects": [
          "Protect continuity in early childhood services",
          "Show the plan for Head Start families",
          "Keep early learning accessible",
          "Do not create gaps in early childhood support",
          "Families need a clear preschool transition plan"
        ],
        "concerns": [
          "Young children need stable relationships and continuity of services.",
          "Families need to know who would provide care and support if district services change.",
          "Preserving some preschool programs does not answer what happens to Head Start families.",
          "Any replacement plan must address affordability, availability, and accessibility.",
          "Early childhood changes deserve their own impact assessment and family input."
        ],
        "facts": [
          "D65 proposes relinquishing Head Start and Early Head Start grants effective July 1, 2028.",
          "The published proposal retains Pre-School for All programming.",
          "The published proposal also retains early childhood special education programming.",
          "The community demand letter calls for student-impact assessments and disclosure of transition costs."
        ],
        "asks": [
          "Please reject the early childhood changes as presented until a funded, publicly reviewed continuity plan is available.",
          "Please publish the number of affected families, services at risk, provider capacity, eligibility rules, and transition costs.",
          "Please work with families, educators, city partners, and potential providers to prevent gaps in early learning and family support.",
          "Please compare alternatives for retaining services before committing to relinquish the grants."
        ]
      },
      {
        "title": "Financial transparency and student impacts",
        "desc": "Show the full savings, costs and student impacts.",
        "topic": "financial transparency and student impacts",
        "closures": false,
        "subjects": [
          "Show the savings and the student impacts",
          "A complete financial plan before closures",
          "Verify the assumptions before voting",
          "Academic outcomes belong in the budget discussion",
          "Compare the full costs of every option"
        ],
        "concerns": [
          "A lower district budget does not by itself establish a better educational outcome.",
          "Projected savings need to include the costs of moving students and programs.",
          "Classroom capacity should reflect actual program needs and support spaces.",
          "Future funding assumptions should be clear to the residents who may be asked to pay.",
          "Lessons from recent transitions should inform the next restructuring decision."
        ],
        "facts": [
          "The published proposal includes approximately $20 million in reductions.",
          "D65 identifies reductions of more than 200 positions across the district.",
          "The demand letter requests projections beyond 2028 and disclosure of reliance on future referenda.",
          "The demand letter asks for academic growth, belonging, attendance, staff stability, and program-access measures following recent transitions."
        ],
        "asks": [
          "Please require an independent review of net recurring savings, one-time costs, enrollment assumptions, and funding risks.",
          "Please publish comparable student-impact assessments for each viable alternative, including class sizes, special education, bilingual services, and school integration.",
          "Please keep closures under a moratorium until financial alternatives and student impacts are verified and discussed with all affected communities.",
          "Please release evidence from recent school transitions and explain how the findings change the current recommendation."
        ]
      }
    ]
  },
  "es": {
    "ui": {
      "h1a": "Escriba a la",
      "h1b": "junta escolar.",
      "lead": "Elija el tema que más le importa y le prepararemos una carta sobre él. Agregue una frase suya y envíela desde su correo. Toma unos dos minutos.",
      "s0": "¿Qué es lo que más le importa?",
      "s0h": "Elija uno. Su carta se centrará en ese tema.",
      "s1": "¿Quién es usted?",
      "name": "Su nombre",
      "namePh": "Nombre y apellido",
      "role": "Soy…",
      "roles": [
        "Madre, padre o cuidador(a) del Distrito 65",
        "Educador(a) o personal del Distrito 65",
        "Miembro de la comunidad a quien le importa el Distrito 65"
      ],
      "s2": "Su carta",
      "to": "Para",
      "toList": "Los 7 miembros de la junta del D65 y schoolboard@district65.net",
      "toNote": "El correo sale de su propia cuenta, así que los miembros de la junta pueden responderle.",
      "subject": "Asunto",
      "body": "Mensaje",
      "shuffle": "↻ Probar otra versión",
      "hint": "Cada carta se arma con distintas piezas sobre el tema que eligió, así que no hay dos iguales. Reemplace el texto entre [corchetes] con una frase suya: las cartas personales tienen más peso.",
      "s3": "Envíela",
      "needName": "Primero escriba su nombre.",
      "brackets": "Su carta todavía tiene texto entre [corchetes]. Reemplácelo con sus propias palabras, o toque el botón otra vez para enviarla así.",
      "opened": "Su correo debería abrirse en otra pestaña o aplicación. Revíselo y presione Enviar. ¡Gracias!",
      "copied": "¡Copiado! Péguelo en un correo nuevo a las direcciones de arriba.",
      "copyFail": "No se pudo copiar automáticamente. Seleccione el mensaje y cópielo a mano.",
      "swapped": "Preparamos una carta nueva para este tema. Los cambios que hizo en la anterior se reemplazaron.",
      "priv": "Privacidad: nada de lo que escribe aquí se guarda ni se nos envía. Esta página solo prepara un correo que usted envía.",
      "copyHead": "Para: ",
      "copySubj": "Asunto: ",
      "greet": "Estimados miembros de la junta:",
      "signoff": "Atentamente,",
      "namePlace": "[Su nombre]",
      "send": "Enviar",
      "copy": "Copiar",
      "copyS": "Para Outlook, Yahoo u otro correo",
      "dsub": "Abre un borrador listo en Gmail",
      "dnote": "Enviar abre Gmail en una pestaña nueva con los destinatarios, el asunto y la carta ya escritos. Solo presione Enviar allí. ¿Usa otro correo? Haga clic en Copiar y pegue todo en un mensaje nuevo.",
      "msub": "Abre su aplicación de correo, lista para enviar",
      "mnote": "Enviar abre la aplicación de correo de su teléfono con todo ya escrito. Solo presione Enviar allí. Si se abre otra aplicación o no pasa nada, toque Copiar y pegue la carta en un correo nuevo."
    },
    "openings": [
      "Les escribo porque {x} debe atenderse antes de que esta propuesta siga adelante.",
      "Les pido que reconsideren la propuesta actual y den {a_x} la revisión pública cuidadosa que merece.",
      "Quiero un distrito sostenible y me preocupa cómo esta propuesta trata {x}."
    ],
    "who": [
      "Me llamo {name}. Soy madre, padre o cuidador(a) de familia del Distrito 65 y quiero que los estudiantes prosperen. [Agregue una frase sobre su hijo o hija o su escuela.]",
      "Me llamo {name}. Soy educador(a) o parte del personal escolar y me importan los estudiantes y las personas que los apoyan. [Agregue una frase sobre su trabajo.]",
      "Me llamo {name}. Soy miembro de la comunidad y me importan las escuelas públicas sólidas y las decisiones públicas responsables. [Agregue una frase sobre por qué esto le importa.]"
    ],
    "common": "Les pido que rechacen la propuesta en su forma actual y establezcan una moratoria sobre el cierre de escuelas hasta que varias alternativas financieramente creíbles, incluida la de mantener todas las escuelas actuales, y su impacto en los estudiantes hayan sido revisados de forma independiente, publicados y discutidos con todas las comunidades afectadas. Les pido también que fijen un plan de trabajo público y etapas de revisión, para que esta pausa produzca un plan mejor y que rinda cuentas.",
    "closings": [
      "Les pido que compartan qué harán para atender estas inquietudes antes de la próxima decisión. Gracias por su tiempo.",
      "Gracias por considerar mis inquietudes y por ayudar a crear un plan que la comunidad pueda entender y apoyar.",
      "Agradecería una respuesta por escrito que explique los próximos pasos y cómo puede participar la comunidad."
    ],
    "issues": [
      {
        "title": "Cierre de escuelas y una moratoria",
        "desc": "Pausar los cierres hasta comparar alternativas reales.",
        "topic": "el cierre de escuelas",
        "closures": true,
        "subjects": [
          "Pausen los cierres hasta verificar las alternativas",
          "Nuestras escuelas merecen un plan completo",
          "Voten no a la propuesta actual de cierres",
          "Comparen alternativas antes de cerrar escuelas",
          "Una moratoria para planificar las escuelas con responsabilidad"
        ],
        "concerns": [
          "Cerrar escuelas antes de comparar a fondo las alternativas podría someter a las familias a trastornos evitables.",
          "Las escuelas que recibirían estudiantes merecen una evaluación clara de personal, espacio y apoyo estudiantil.",
          "Las escuelas de barrio a las que se llega caminando importan a familias de todo el distrito.",
          "Conservar un edificio no garantiza que vuelva a abrir como escuela.",
          "Los estudiantes no deberían cargar con los riesgos de suposiciones que no han sido verificadas de forma independiente."
        ],
        "facts": [
          "El D65 propone cerrar Dewey y Lincolnwood al final del año escolar 2026–27.",
          "El D65 describe la votación del 9 de noviembre como una votación sobre el plan, a la que todavía seguirían audiencias sobre los cierres y una decisión final posterior.",
          "El distrito propone conservar ambos terrenos escolares y estudiar un posible referéndum de bonos en noviembre de 2028.",
          "La carta de demandas de la comunidad pide comparar varias opciones sostenibles, incluida la de mantener todas las escuelas actuales."
        ],
        "asks": [
          "Les pido que establezcan una moratoria sobre los cierres hasta que las alternativas verificadas y su impacto en los estudiantes hayan sido revisados públicamente por todas las comunidades afectadas.",
          "Les pido que publiquen opciones comparables, incluida la de mantener todas las escuelas actuales, con sus ahorros recurrentes, costos de transición y efectos educativos.",
          "Les pido que exijan una revisión independiente del impacto financiero y estudiantil antes de aprobar cualquier cierre definitivo, con etapas de revisión pública.",
          "Les pido que voten no a la propuesta tal como está y que encarguen un proceso conjunto con la comunidad para elaborar una alternativa financieramente creíble."
        ]
      },
      {
        "title": "Participación comunitaria y planificación compartida",
        "desc": "Dar a cada comunidad una voz real en el plan.",
        "topic": "la participación comunitaria",
        "closures": false,
        "subjects": [
          "Den a cada comunidad una voz significativa",
          "Construyan el plan con la comunidad",
          "La opinión de la comunidad debe poder cambiar el resultado",
          "Una visión compartida antes de cambios permanentes",
          "Incluyan a las familias antes de decidir"
        ],
        "concerns": [
          "Una reunión sobre cómo implementar una propuesta no es lo mismo que una oportunidad para dar forma a las alternativas.",
          "Las familias de las escuelas que recibirían estudiantes necesitan la misma oportunidad de entender e influir en los cambios.",
          "Los residentes sin hijos inscritos también tienen interés en el futuro del distrito.",
          "El idioma, los horarios de trabajo y la accesibilidad para personas con discapacidad no deberían determinar qué voces se escuchan.",
          "Las opiniones del público necesitan una conexión visible con las decisiones de la junta."
        ],
        "facts": [
          "La carta de demandas pide la participación de residentes de todo Evanston y Skokie, incluidos quienes no tienen hijos inscritos.",
          "El plan del D65 incluye cierres, cambios de límites escolares y reducciones de personal en todo el distrito.",
          "El distrito ha publicado versiones del 13 y del 23 de octubre de sus límites escolares propuestos.",
          "La carta de demandas pide que se examinen públicamente las consecuencias educativas y financieras de las alternativas."
        ],
        "asks": [
          "Les pido que creen un grupo de trabajo de la junta, el distrito, la ciudad y la comunidad, con familias, educadores y expertos financieros independientes.",
          "Les pido que mantengan en pausa los cierres de escuelas mientras todas las comunidades afectadas revisan y discuten alternativas creíbles.",
          "Les pido que ofrezcan oportunidades accesibles y en varios idiomas para dar forma a las opciones, y que publiquen cómo esas opiniones cambian la recomendación.",
          "Les pido que publiquen un calendario de decisiones que permita revisar a fondo los datos y las alternativas antes de las votaciones finales."
        ]
      },
      {
        "title": "Coordinación con la ciudad y acceso a las escuelas del barrio",
        "desc": "Planificar juntas escuelas, vivienda y transporte.",
        "topic": "la coordinación entre la ciudad y el distrito",
        "closures": false,
        "subjects": [
          "Planifiquen juntas las escuelas y la vivienda",
          "Coordinen antes de definir los límites escolares",
          "Protejan el acceso a las escuelas del barrio",
          "Una sola comunidad necesita una planificación coordinada",
          "Estudien los efectos en toda la ciudad antes de seguir"
        ],
        "concerns": [
          "El crecimiento de la vivienda y el acceso a las escuelas deberían evaluarse juntos.",
          "Trayectos más largos a la escuela podrían dificultar que las familias vivan con menos viajes en auto.",
          "Los ahorros del distrito deberían considerarse junto con cualquier costo nuevo de infraestructura para la ciudad.",
          "Las familias en viviendas asequibles merecen un acceso práctico a las escuelas y los programas.",
          "Arreglar los problemas de tráfico después de decidir podría hacer perder mejores opciones al principio del proceso."
        ],
        "facts": [
          "Evanston adoptó su nuevo plan integral el 26 de enero de 2026.",
          "La propuesta del D65 cambia los límites escolares más allá de las dos escuelas que propone cerrar.",
          "La propuesta del 23 de octubre asigna el programa TWI de Dewey a Lincoln y el programa STEP de Lincolnwood a Orrington.",
          "Las preguntas frecuentes del D65 distinguen las proyecciones de población general de los pronósticos de matrícula en edad escolar."
        ],
        "asks": [
          "Les pido que encarguen una evaluación conjunta de la ciudad y el distrito sobre el crecimiento de la vivienda, el acceso a las escuelas, el transporte y la infraestructura antes de decidir los cierres.",
          "Les pido que superpongan los límites propuestos con los proyectos de vivienda aprobados, la vivienda asequible y las rutas reales a pie, y que publiquen los resultados.",
          "Les pido que concilien las suposiciones de crecimiento de la ciudad con los pronósticos de matrícula del distrito, con estimaciones realistas para viviendas familiares.",
          "Les pido que apoyen una moratoria sobre los cierres hasta que las alternativas y su impacto en los estudiantes de toda la ciudad estén verificados y se hayan discutido con las comunidades afectadas."
        ]
      },
      {
        "title": "Cuidado infantil escolar (SACC)",
        "desc": "Mantener un cuidado confiable y asequible para familias que trabajan.",
        "topic": "el cuidado infantil escolar (SACC)",
        "closures": false,
        "subjects": [
          "Mantengan SACC al alcance de las familias que trabajan",
          "Protejan un cuidado infantil escolar confiable",
          "Muestren el plan de cuidado infantil antes de cerrar SACC",
          "Las familias que trabajan necesitan cuidado asequible",
          "No dejen a las familias sin cuidado infantil"
        ],
        "concerns": [
          "Las familias necesitan un cuidado confiable para mantener sus horarios de trabajo.",
          "Una alternativa solo funciona si las familias pueden pagarla y conseguir un lugar.",
          "Los niños con discapacidades necesitan un cuidado que pueda atender sus necesidades.",
          "Cambiar de escuela y de cuidado infantil al mismo tiempo podría agravar los trastornos.",
          "Las familias no deberían tener que tomar decisiones de empleo sin información clara sobre el cuidado futuro."
        ],
        "facts": [
          "El D65 propone cerrar su programa de cuidado infantil escolar (SACC) al final del año escolar 2026–27.",
          "El cierre de SACC aparece por separado de los cierres de escuelas primarias propuestos.",
          "La carta de demandas pide que se den a conocer los costos de transición y alternativas creíbles.",
          "La carta de demandas pide una participación significativa de comunidades de todo Evanston y Skokie."
        ],
        "asks": [
          "Les pido que rechacen el cierre de SACC tal como está propuesto y evalúen opciones para mantener un cuidado asequible y accesible.",
          "Les pido que publiquen la capacidad de reemplazo, las tarifas, los subsidios, los horarios, los lugares y los apoyos para discapacidades antes de cualquier decisión sobre SACC.",
          "Les pido que trabajen con las familias, el personal de SACC, la ciudad y posibles proveedores para comparar opciones de servicio sostenibles.",
          "Les pido que exijan un plan de continuidad con fondos para que cada familia atendida hoy tenga una opción de cuidado realista antes de que terminen los servicios del distrito."
        ]
      },
      {
        "title": "TWI y participación de padres bilingües",
        "desc": "Dar voz a las familias bilingües antes de mudar el TWI.",
        "topic": "la participación de los padres bilingües en el programa TWI",
        "closures": false,
        "subjects": [
          "Resuelvan las dudas sobre el BPAC antes de mudar el TWI",
          "Den voz a las familias bilingües en la planificación del programa",
          "Que las decisiones sobre el TWI rindan cuentas a las familias",
          "Revisen el proceso para mudar el TWI de Dewey",
          "Pausen el traslado del TWI hasta una revisión significativa"
        ],
        "concerns": [
          "Mudar un programa bilingüe puede afectar el acceso, las relaciones, el personal y la participación de las familias.",
          "Las familias deberían poder discutir la opción de mantener el TWI en Dewey, además de otras opciones.",
          "La falta de un BPAC (comité asesor de padres bilingües) activo deja preguntas sin resolver sobre el proceso de planificación del programa.",
          "Una reunión centrada en un posible cierre quizás no ofrezca una comparación completa de las alternativas para el programa.",
          "Las familias necesitan saber cómo llegarán sus opiniones a la junta antes de que actúe."
        ],
        "facts": [
          "La propuesta del 23 de octubre trasladaría el programa TWI de Dewey a Lincoln.",
          "En un correo del 29 de octubre, Cecilia Romero indicó que el D65 no tiene un BPAC activo.",
          "En su respuesta del 30 de octubre, Cecilia Romero dijo que no hay un calendario fijo para restablecer formalmente el BPAC.",
          "Cecilia Romero dijo que ISBE sabe que el BPAC está inactivo; los correos que han visto las familias no incluyen orientación específica sobre este traslado."
        ],
        "asks": [
          "Les pido que pausen la aprobación del traslado del TWI hasta que se aclaren los requisitos de participación de los padres y las familias afectadas puedan revisar a fondo las alternativas.",
          "Les pido que compartan la orientación de ISBE en la que se basan y aclaren si trata específicamente el traslado del TWI de Dewey.",
          "Les pido que publiquen una evaluación del impacto en el programa bilingüe que cubra acceso, matrícula, personal, equilibrio de idiomas y continuidad.",
          "Les pido que establezcan un calendario verificable para reconstruir el BPAC y expliquen cómo influirán en la decisión las recomendaciones de las familias bilingües."
        ]
      },
      {
        "title": "Primera infancia y Head Start",
        "desc": "Proteger la continuidad para niños pequeños y sus familias.",
        "topic": "los servicios de primera infancia",
        "closures": false,
        "subjects": [
          "Protejan la continuidad de los servicios de primera infancia",
          "Muestren el plan para las familias de Head Start",
          "Mantengan accesible el aprendizaje temprano",
          "No creen vacíos en el apoyo a la primera infancia",
          "Las familias necesitan un plan claro de transición preescolar"
        ],
        "concerns": [
          "Los niños pequeños necesitan relaciones estables y continuidad en los servicios.",
          "Las familias necesitan saber quién daría cuidado y apoyo si cambian los servicios del distrito.",
          "Conservar algunos programas preescolares no responde qué pasará con las familias de Head Start.",
          "Cualquier plan de reemplazo debe atender el costo, la disponibilidad y la accesibilidad.",
          "Los cambios en la primera infancia merecen su propia evaluación de impacto y la opinión de las familias."
        ],
        "facts": [
          "El D65 propone renunciar a las subvenciones de Head Start y Early Head Start a partir del 1 de julio de 2028.",
          "La propuesta publicada conserva el programa Pre-School for All.",
          "La propuesta publicada también conserva los programas de educación especial para la primera infancia.",
          "La carta de demandas de la comunidad pide evaluaciones del impacto en los estudiantes y que se den a conocer los costos de transición."
        ],
        "asks": [
          "Les pido que rechacen los cambios en la primera infancia tal como están hasta que exista un plan de continuidad con fondos y revisado públicamente.",
          "Les pido que publiquen el número de familias afectadas, los servicios en riesgo, la capacidad de los proveedores, las reglas de elegibilidad y los costos de transición.",
          "Les pido que trabajen con las familias, los educadores, la ciudad y posibles proveedores para evitar vacíos en el aprendizaje temprano y el apoyo a las familias.",
          "Les pido que comparen alternativas para conservar los servicios antes de comprometerse a renunciar a las subvenciones."
        ]
      },
      {
        "title": "Transparencia financiera e impacto en los estudiantes",
        "desc": "Mostrar los ahorros, los costos y el impacto completos.",
        "topic": "la transparencia financiera y el impacto en los estudiantes",
        "closures": false,
        "subjects": [
          "Muestren los ahorros y el impacto en los estudiantes",
          "Un plan financiero completo antes de los cierres",
          "Verifiquen las suposiciones antes de votar",
          "Los resultados académicos deben ser parte del debate del presupuesto",
          "Comparen el costo total de cada opción"
        ],
        "concerns": [
          "Un presupuesto más bajo no garantiza por sí solo un mejor resultado educativo.",
          "Los ahorros proyectados deben incluir el costo de trasladar estudiantes y programas.",
          "La capacidad de las aulas debería reflejar las necesidades reales de los programas y los espacios de apoyo.",
          "Las suposiciones sobre fondos futuros deberían ser claras para los residentes a quienes se les podría pedir que paguen.",
          "Las lecciones de las transiciones recientes deberían guiar la próxima decisión de reestructuración."
        ],
        "facts": [
          "La propuesta publicada incluye unos 20 millones de dólares en reducciones.",
          "El D65 identifica la reducción de más de 200 puestos en todo el distrito.",
          "La carta de demandas pide proyecciones más allá de 2028 y que se informe cuánto dependen de futuros referéndums.",
          "La carta de demandas pide medidas de crecimiento académico, sentido de pertenencia, asistencia, estabilidad del personal y acceso a programas después de las transiciones recientes."
        ],
        "asks": [
          "Les pido que exijan una revisión independiente de los ahorros recurrentes netos, los costos únicos, las suposiciones de matrícula y los riesgos de financiamiento.",
          "Les pido que publiquen evaluaciones comparables del impacto en los estudiantes para cada alternativa viable, incluidos el tamaño de las clases, la educación especial, los servicios bilingües y la integración escolar.",
          "Les pido que mantengan una moratoria sobre los cierres hasta que las alternativas financieras y su impacto en los estudiantes estén verificados y se hayan discutido con todas las comunidades afectadas.",
          "Les pido que den a conocer la evidencia de las transiciones escolares recientes y expliquen cómo esos hallazgos cambian la recomendación actual."
        ]
      }
    ]
  }
};
