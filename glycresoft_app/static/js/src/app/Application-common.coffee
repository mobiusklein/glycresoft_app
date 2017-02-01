class Application extends ActionLayerManager
    constructor: (options={}) ->
        super options.actionContainer, options

        @version = [
            0
            0
            1
        ]

        @context = {}
        @settings = {}
        @tasks = {}
        @sideNav = $('.side-nav')
        @colors = new ColorManager()
        self = this

        self.monosaccharideFilterState = new MonosaccharideFilterState(self, null)

        @messageHandlers = {}
        
        @connectEventSource()
        
        @handleMessage 'update', (data) =>
            Materialize.toast data.replace(/"/g, ''), 4000
            return

        @handleMessage 'task-queued', (data) =>
            self.tasks[data.id] =
                'id': data.id
                'name': data.name
                "created_at": data.created_at
                'status': 'queued'
            self.updateTaskList()
            return
        @handleMessage 'task-start', (data) =>
            self.tasks[data.id] =
                'id': data.id
                'name': data.name
                "created_at": data.created_at
                'status': 'running'
            self.updateTaskList()
            return
        @handleMessage 'task-error', (data) =>
            task = self.tasks[data.id]
            task.status = 'error'
            self.updateTaskList()
            return
        @handleMessage 'task-complete', (data) =>
            try
                self.tasks[data.id].status = 'finished'
            catch err
                self.tasks[data.id] =
                    'id': data.id
                    'name': data.name
                    "created_at": data.created_at
                    'status': 'finished'
            self.updateTaskList()
            return
        @handleMessage "task-stopped", (data) =>
            try
                self.tasks[data.id].status = 'stopped'
            catch err
                self.tasks[data.id] =
                    'id': data.id
                    'name': data.name
                    'status': 'stopped'
            self.updateTaskList()
            return            
        @handleMessage 'new-sample-run', (data) =>
            @samples[data.name] = data
            @emit "render-samples"
        @handleMessage 'new-hypothesis', (data) =>
            @hypotheses[data.uuid] = data
            @emit "render-hypotheses"
        @handleMessage 'new-analysis', (data) =>
            @analyses[data.id] = data
            @emit "render-analyses"

        @on "layer-change", (data) =>
            @colors.update()

    connectEventSource: ->
        @eventStream = new EventSource('/stream')

    runInitializers: ->
        for initializer in Application.initializers
            initializer.apply this, null 

    updateSettings: (payload={}) ->
        $.post('/preferences', payload).success((data) =>
            for k, v of data
                @settings[k] = v
            @emit("update_settings")
        ).error (err) ->
            console.log "error in updateSettings", err, arguments

    updateTaskList: (clearFinished=true) ->
        taskListContainer = @sideNav.find('.task-list-container ul')

        clickTask = (event) ->
            handle = $(this)
            state = handle.attr('data-status')
            id = handle.attr('data-id')
            if (state == 'finished' or state == 'stopped') and event.which != 3
                delete self.tasks[id]
                handle.fadeOut()
                handle.remove()
            return
        self = @

        viewLog = (event) ->
            handle = $(this)    
            id = handle.attr('data-id')
            name = handle.attr("data-name")
            createdAt = handle.attr("data-created_at")
            state = {}
            modal = $("#message-modal")
            updateWrapper = () ->
                updater = ->
                    $.get("/internal/log/#{name}-#{createdAt}").success(
                        (message) ->
                            modal.find(".modal-content").html message
                        )
                state.intervalId = setInterval(updater, 5000)
            completer = ->
                clearInterval(state.intervalId)

            $.get("/internal/log/#{name}-#{createdAt}").success(
                (message) => self.displayMessageModal(message, {
                    "ready": updateWrapper, "complete": completer})).error(
                (err) => alert("An error occurred during retrieval. #{err.toString()}"))

        cancelTask = (event) ->
            userInput = window.confirm("Are you sure you want to cancel this task?")
            if userInput
                handle = $(this)
                id = handle.attr('data-id')
                $.get "/internal/cancel_task/" + id

        taskListContainer.html("")
        taskListContainer.append(_.map(@tasks, renderTask))
        taskListContainer.find('li').map (i, li) -> contextMenu li, {
            "View Log": viewLog
            "Cancel Task": cancelTask
        }
        taskListContainer.find('li').click clickTask
        taskListContainer.find("li").dblclick viewLog

    handleMessage: (messageType, handler) ->
        @messageHandlers[messageType] = handler
        @eventStream.addEventListener messageType, (event) ->
            data = JSON.parse(event.data)
            handler(data)

    @initializers = [
        ->
            self = @
            $ ->
                self.container = $(self.options.actionContainer)
                self.sideNav = $('.side-nav')
                self.addLayer ActionBook.home
                $("#search-glycan-composition").click (event) ->
                    self.addLayer ActionBook.glycanCompositionSearch
                    self.setShowingLayer self.lastAdded
                $("#search-glycopeptide-database").click (event) ->
                    self.addLayer ActionBook.glycopeptideSequenceSearch
                    self.setShowingLayer self.lastAdded
                $("#add-sample").click (event) ->
                    self.addLayer ActionBook.addSample
                    self.setShowingLayer self.lastAdded
                $("#build-glycan-search-space").click (event) ->
                    self.addLayer ActionBook.naiveGlycanSearchSpace
                    self.setShowingLayer self.lastAdded
                $("#build-glycopeptide-search-space").click (event) ->
                    self.addLayer ActionBook.naiveGlycopeptideSearchSpace
                    self.setShowingLayer self.lastAdded
        ->
            @loadData()
        ->
            @handleMessage "files-to-download", (data) =>
                for file in data.files
                    @downloadFile(file)
        ->
            @on "update_settings", =>
                layer = @getShowingLayer()
                if layer.name != ActionBook.home.name
                    console.log("Updated Settings, Current Layer:", layer.name)
                    layer.setup()

        ->
            setInterval(@_upkeepIntervalCallback, @options.upkeepInterval || 10000)

            refreshTasks = =>
                Task.all (d) =>
                    for key, task of d
                        @tasks[key] = task
                    @updateTaskList()

            setInterval(refreshTasks, @options.refreshTasksInterval || 250000)
    ]

    loadData: ->
        Hypothesis.all (d) => 
            @hypotheses = d
            @emit "render-hypotheses"
        Sample.all (d) =>
            @samples = d
            @emit "render-samples"
        Analysis.all (d) =>
            @analyses = d
            @emit "render-analyses"
        Task.all (d) =>
            @tasks = d
            @updateTaskList()
        @colors.update()

    downloadFile: (filePath) ->
        window.location = "/internal/file_download/" + btoa(filePath)

    displayMessageModal: (message, modalArgs) ->
        container = $("#message-modal")
        container.find('.modal-content').html message
        container.openModal(modalArgs)

    closeMessageModal: ->
        container = $("#message-modal")
        container.closeModal()

    ajaxWithContext: (url, options) ->
        if !options?
            options = {data:{}}
        data = options.data
        data['settings'] = @settings
        data['context'] = @context
        options.method = "POST"
        options.data = JSON.stringify(data)
        options.contentType = "application/json"
        return $.ajax(url, options)

    _upkeepIntervalCallback: =>
        if @eventStream.readyState == 2
            console.log "Re-establishing EventSource"
            @connectEventSource()
            for msgType, handler of @messageHandlers
                @handleMessage msgType, handler
        return true

    setHypothesisContext: (hypothseisUUID) ->
        @context.hypothseisUUID = hypothseisUUID

    invalidate: ->
        @monosaccharideFilterState.invalidate()
        console.log("Invalidated")


renderTask = (task) ->
    name = task.name
    status = task.status
    id = task.id
    created_at = task.created_at
    element = $("<li data-id=\'#{id}\' data-status=\'#{status}\' data-name=\'#{name}\' data-created_at=\'#{created_at}\'><b>#{name}</b> (#{status})</li>")
    element.attr("data-name", name)
    element


$(() ->
    if not window.ApplicationConfiguration?
        window.ApplicationConfiguration = {
            refreshTasksInterval: 25000,
            upkeepInterval: 10000,
        }

    window.GlycReSoft = new Application(options={
        actionContainer: ".action-layer-container",
        refreshTasksInterval: window.ApplicationConfiguration.refreshTasksInterval,
        upkeepInterval: window.ApplicationConfiguration.upkeepInterval,
    })
    window.onerror = (msg, url, line, col, error) ->
        console.log(msg, url, line, col, error)
        GlycReSoft.ajaxWithContext(ErrorLogURL, {
            data: [msg, url, line, col, error]
        })
        return false
    GlycReSoft.runInitializers()
    GlycReSoft.updateSettings()
    GlycReSoft.updateTaskList())
